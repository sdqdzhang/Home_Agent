from __future__ import annotations

import uuid
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
    ) -> dict[str, Any]:
        if use_model:
            return await self._run_with_model(url, task, config)
        return await self._run_without_model(url, task, config)

    async def _run_without_model(
        self,
        url: str,
        task: str = "",
        config: dict | None = None,
    ) -> dict[str, Any]:
        """纯规则爬取：引擎 success 判定 + 过滤器最高分，不调用 LLM。"""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        cfg = dict(config or {})
        task_desc = task or f"抓取并提取 {url} 的有效内容"
        logger = JobLogger(crawler_settings.logs_dir, job_id)
        self.store.create_job(job_id, url, cfg)

        logger.info(f"[无模型] 任务开始: {url}")
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
                    strategy = alt
            if result.success:
                logger.info(f"引擎判定成功: {result.strategy}")
                break
            err = result.error or "内容为空"
            attempts.append((result.strategy, err))
            logger.warning(f"引擎失败: {err}")

        if (not result or not result.success) and cfg.get("verify_ssl", True):
            if any("CERTIFICATE_VERIFY_FAILED" in e or "certificate verify failed" in e.lower() for _, e in attempts):
                logger.warning("检测到 SSL 证书错误，自动以 verify_ssl=False 重试")
                cfg["verify_ssl"] = False
                attempts.clear()
                for strategy in strategies:
                    logger.info(f"SSL 跳过重试: {strategy}")
                    result = await ENGINE_MAP[strategy](url, cfg)
                    if result.success:
                        logger.info(f"引擎判定成功: {result.strategy}")
                        break
                    attempts.append((result.strategy, result.error or "内容为空"))
                    logger.warning(f"引擎失败: {result.error or '内容为空'}")

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
    ) -> dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        cfg = dict(config or {})
        task_desc = task or f"抓取并提取 {url} 的有效内容"
        logger = JobLogger(crawler_settings.logs_dir, job_id)
        self.store.create_job(job_id, url, cfg)

        logger.info(f"任务开始: {url}")
        logger.info(f"任务描述: {task_desc}")

        primary = classify_url(url)
        strategies = fallback_order(primary)
        logger.info(f"策略顺序: {strategies}")

        result: CrawlResult | None = None
        judge: dict[str, Any] = {"success": False}

        for attempt in range(crawler_settings.max_retries):
            for strategy in strategies:
                logger.info(f"尝试策略 {strategy} (第 {attempt + 1} 轮)")
                engine = ENGINE_MAP[strategy]
                result = await engine(url, cfg)

                if result.metadata.get("content_type"):
                    alt = classify_response(result.metadata["content_type"], result.html[:3000])
                    if alt and alt != strategy:
                        logger.info(f"响应头建议切换为 {alt}")
                        result = await ENGINE_MAP[alt](url, cfg)
                        strategy = alt

                judge = await self.assistant.judge_crawl(task=task_desc, url=url, result=result)
                logger.info(f"模型判断: success={judge.get('success')} reason={judge.get('reason')}")

                if judge.get("success"):
                    self.store.update_job(job_id, status="crawled", strategy=result.strategy)
                    break

                suggestions = judge.get("suggestions") or {}
                if suggestions or result.error:
                    logger.warning(f"调参重试: {suggestions or result.error}")
                    cfg = await self.assistant.tune_config(
                        url=url,
                        strategy=result.strategy,
                        config=cfg,
                        error=result.error,
                        suggestions=suggestions,
                    )
                    logger.info(f"新配置: {cfg}")

            if judge.get("success") and result:
                break

        if not result:
            logger.error("无爬取结果")
            self.store.update_job(job_id, status="failed", summary="无爬取结果")
            return self._build_response(job_id, logger, success=False, error="无爬取结果")

        # 过滤阶段
        logger.info("运行预设过滤器")
        filtered = [fn(result) for fn in ALL_FILTERS]
        for item in filtered:
            logger.debug(f"过滤器 {item.name}: score={item.score}")

        pick = await self.assistant.pick_best_filter(task=task_desc, url=url, candidates=filtered)
        best_name = pick.get("best_name")
        best = next((f for f in filtered if f.name == best_name), None)

        final_content = ""
        success = bool(pick.get("success"))

        if success and best:
            final_content = best.content
            logger.info(f"选中过滤器: {best_name}")
        else:
            logger.warning("预设过滤未满足，启用模型自行过滤")
            custom = await self.assistant.custom_filter(task=task_desc, url=url, result=result)
            success = bool(custom.get("success"))
            final_content = custom.get("result", "")
            logger.info(f"模型过滤: success={success}")

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
