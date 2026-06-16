from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from modules.crawler.config import crawler_settings
from modules.crawler.filters import ALL_FILTERS
from modules.crawler.logging import JobLogger
from modules.crawler.model import CrawlerAssistant
from modules.crawler.storage import JobStore
from modules.crawler.strategies import (
    CrawlResult,
    classify_url,
    crawl_feed,
    crawl_httpx_bs4,
    crawl_playwright,
    fallback_order,
)
from modules.crawler.strategies.router import classify_response

logger = logging.getLogger(__name__)

ENGINE_MAP = {
    "feedparser": crawl_feed,
    "httpx_bs4": crawl_httpx_bs4,
    "playwright": crawl_playwright,
}


def _summarize_errors(attempts: list[tuple[str, str]]) -> str:
    """汇总各引擎失败原因并给出可操作建议。"""
    lines = [f"{name}: {err}" for name, err in attempts if err]
    text = " | ".join(lines) if lines else "未知错误"
    hints: list[str] = []
    joined = " ".join(lines).lower()
    if "certificate" in joined or "ssl" in joined:
        hints.append("目标站 SSL 证书异常，可勾选「忽略 SSL 证书错误」或在 config 中设 verify_ssl=false")
    if "executable doesn't exist" in joined or "playwright install" in joined:
        hints.append("运行 playwright install chromium 安装浏览器")
    if hints:
        return f"{text} —— 建议: {'; '.join(hints)}"
    return text


class CrawlOrchestrator:
    """爬取主流程：策略路由 →（可选）模型判断/调参 → 过滤 →（可选）模型择优/兜底。"""

    def __init__(self, store: JobStore, assistant: CrawlerAssistant | None = None) -> None:
        self.store = store
        self.assistant = assistant or CrawlerAssistant()

    async def run(
        self,
        url: str,
        task: str = "",
        config: dict | None = None,
        *,
        use_model: bool = True,
        log_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        if use_model:
            return await self._run_with_model(url, task, config, log_callback=log_callback)
        return await self._run_without_model(url, task, config, log_callback=log_callback)

    def _make_logger(self, job_id: str, log_callback: Callable[[str], None] | None) -> JobLogger:
        return JobLogger(crawler_settings.logs_dir, job_id, on_line=log_callback)

    async def _crawl_with_engines(
        self,
        url: str,
        cfg: dict,
        logger: JobLogger,
    ) -> tuple[CrawlResult | None, list[tuple[str, str]]]:
        """按策略顺序爬取，返回最佳结果与各引擎失败记录。"""
        strategies = fallback_order(classify_url(url))
        logger.info(f"策略顺序: {strategies}")

        result: CrawlResult | None = None
        attempts: list[tuple[str, str]] = []
        for strategy in strategies:
            logger.info(f"尝试策略: {strategy}")
            result = await ENGINE_MAP[strategy](url, cfg)
            if result.metadata.get("content_type"):
                alt = classify_response(result.metadata["content_type"], result.html[:3000])
                if alt and alt != strategy:
                    logger.info(f"响应头建议切换为 {alt}")
                    result = await ENGINE_MAP[alt](url, cfg)
            if result.success:
                logger.info(f"引擎判定成功: {result.strategy}")
                return result, attempts
            err = result.error or "内容为空"
            attempts.append((result.strategy, err))
            logger.warning(f"引擎失败: {err}")

        if cfg.get("verify_ssl", True) and any(
            "CERTIFICATE_VERIFY_FAILED" in e or "certificate verify failed" in e.lower() for _, e in attempts
        ):
            logger.warning("检测到 SSL 证书错误，自动以 verify_ssl=False 重试")
            cfg["verify_ssl"] = False
            attempts.clear()
            for strategy in strategies:
                logger.info(f"SSL 跳过重试: {strategy}")
                result = await ENGINE_MAP[strategy](url, cfg)
                if result.success:
                    logger.info(f"引擎判定成功: {result.strategy}")
                    return result, attempts
                attempts.append((result.strategy, result.error or "内容为空"))
                logger.warning(f"引擎失败: {result.error or '内容为空'}")

        return result, attempts

    async def _run_without_model(
        self,
        url: str,
        task: str = "",
        config: dict | None = None,
        *,
        log_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """纯规则爬取：引擎 success 判定 + 过滤器最高分，不调用 LLM。"""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        cfg = dict(config or {})
        task_desc = task or f"抓取并提取 {url} 的有效内容"
        logger = self._make_logger(job_id, log_callback)
        self.store.create_job(job_id, url, cfg)

        logger.info(f"[无模型] 任务开始: {url}")
        result, attempts = await self._crawl_with_engines(url, cfg, logger)

        if not result or not result.success:
            err = _summarize_errors(attempts) if attempts else (result.error if result else "无爬取结果")
            logger.error(f"所有策略均未成功: {err}")
            self.store.update_job(job_id, status="failed", summary=err)
            return self._build_response(job_id, logger, success=False, error=err, crawl_result=result)

        logger.info("运行预设过滤器（按最高分选取）")
        filtered = [fn(result) for fn in ALL_FILTERS]
        best = max(filtered, key=lambda f: f.score)
        final_content = best.content if best.score > 0 else result.text
        success = bool(final_content.strip())
        logger.info(f"选中过滤器: {best.name} (score={best.score})")

        artifact = {
            "job_id": job_id,
            "url": url,
            "task": task_desc,
            "strategy": result.strategy,
            "success": success,
            "mode": "without_model",
            "title": result.title,
            "content": final_content,
            "crawl_preview": result.preview(1000),
            "filters": [{"name": f.name, "score": f.score} for f in filtered],
            "picked_filter": best.name,
        }
        path = self.store.save_artifact(job_id, artifact)
        self.store.update_job(
            job_id,
            status="completed" if success else "failed",
            strategy=result.strategy,
            result_path=str(path),
            summary=f"{'成功' if success else '失败'}: {result.title or url}",
            config=cfg,
        )
        logger.info(f"任务结束: success={success}")
        return self._build_response(job_id, logger, success=success, result=artifact, crawl_result=result)

    async def _run_with_model(
        self,
        url: str,
        task: str = "",
        config: dict | None = None,
        *,
        log_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        cfg = dict(config or {})
        task_desc = task or f"抓取并提取 {url} 的有效内容"
        logger = self._make_logger(job_id, log_callback)
        self.store.create_job(job_id, url, cfg)

        logger.info(f"任务开始: {url}")
        logger.info(f"任务描述: {task_desc}")

        result, attempts = await self._crawl_with_engines(url, cfg, logger)
        if not result or not result.success:
            err = _summarize_errors(attempts) if attempts else (result.error if result else "无爬取结果")
            logger.error(f"所有策略均未成功: {err}")
            self.store.update_job(job_id, status="failed", summary=err)
            return self._build_response(job_id, logger, success=False, error=err, crawl_result=result)

        self.store.update_job(job_id, status="crawled", strategy=result.strategy)

        judge: dict[str, Any] = {"success": False, "reason": "skipped"}
        logger.info("调用模型判断爬取结果（引擎已成功，失败时将回退规则过滤）")
        try:
            judge = await self.assistant.judge_crawl(task=task_desc, url=url, result=result)
            logger.info(f"模型判断: success={judge.get('success')} reason={judge.get('reason')}")
            if not judge.get("success"):
                logger.warning("模型判断未通过，但引擎已成功，继续过滤阶段")
        except Exception as exc:
            logger.warning(f"模型判断异常({exc})，使用引擎结果继续")

        if not judge.get("success") and result.error:
            try:
                suggestions = judge.get("suggestions") or {}
                logger.warning(f"尝试模型调参: {suggestions or result.error}")
                cfg = await self.assistant.tune_config(
                    url=url,
                    strategy=result.strategy,
                    config=cfg,
                    error=result.error,
                    suggestions=suggestions,
                )
                retry, _ = await self._crawl_with_engines(url, cfg, logger)
                if retry and retry.success:
                    result = retry
                    self.store.update_job(job_id, strategy=result.strategy)
            except Exception as exc:
                logger.warning(f"模型调参重试失败({exc})")

        logger.info("运行预设过滤器")
        filtered = [fn(result) for fn in ALL_FILTERS]
        for item in filtered:
            logger.debug(f"过滤器 {item.name}: score={item.score}")

        best_rule = max(filtered, key=lambda f: f.score)
        pick: dict[str, Any] = {"success": False}
        logger.info("调用模型择优过滤器（失败时回退最高分）")
        try:
            pick = await self.assistant.pick_best_filter(task=task_desc, url=url, candidates=filtered)
        except Exception as exc:
            logger.warning(f"模型择优异常({exc})")

        best_name = pick.get("best_name")
        best = next((f for f in filtered if f.name == best_name), None)
        final_content = ""
        success = False
        picked_by = ""

        if pick.get("success") and best:
            final_content = best.content
            success = bool(final_content.strip())
            picked_by = best_name or best.name
            logger.info(f"模型选中过滤器: {picked_by}")
        elif best_rule.score > 0:
            final_content = best_rule.content
            success = bool(final_content.strip())
            picked_by = best_rule.name
            logger.info(f"回退最高分过滤器: {picked_by} (score={best_rule.score})")
        elif result.text.strip():
            logger.warning("预设过滤未满足，尝试模型自行过滤")
            try:
                custom = await self.assistant.custom_filter(task=task_desc, url=url, result=result)
                success = bool(custom.get("success"))
                final_content = custom.get("result", "") or result.text
                picked_by = "custom_filter"
                logger.info(f"模型过滤: success={success}")
            except Exception as exc:
                logger.warning(f"模型过滤异常({exc})，使用引擎正文")
                final_content = result.text
                success = True
                picked_by = "engine_text"
        else:
            success = False

        artifact = {
            "job_id": job_id,
            "url": url,
            "task": task_desc,
            "strategy": result.strategy,
            "success": success,
            "mode": "with_model",
            "title": result.title,
            "content": final_content,
            "crawl_preview": result.preview(1000),
            "filters": [{"name": f.name, "score": f.score} for f in filtered],
            "picked_filter": picked_by,
            "judge": judge,
            "pick": pick,
        }
        path = self.store.save_artifact(job_id, artifact)
        self.store.update_job(
            job_id,
            status="completed" if success else "failed",
            strategy=result.strategy,
            result_path=str(path),
            summary=f"{'成功' if success else '失败'}: {result.title or url}",
            config=cfg,
        )
        logger.info(f"任务结束: success={success}, artifact={path}")

        return self._build_response(
            job_id,
            logger,
            success=success,
            result=artifact,
            crawl_result=result,
        )

    def _build_response(
        self,
        job_id: str,
        logger: JobLogger,
        *,
        success: bool,
        result: dict | None = None,
        crawl_result: CrawlResult | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        return {
            "job_id": job_id,
            "success": success,
            "error": error,
            "result": result,
            "log": logger.lines,
            "log_path": str(logger.log_path),
            "title": crawl_result.title if crawl_result else "",
        }
