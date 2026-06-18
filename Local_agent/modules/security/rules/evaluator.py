from __future__ import annotations

from modules.security.rules.commands import is_black_command, is_white_command
from modules.security.rules.paths import extract_paths, find_black_directories, only_white_directories
from modules.security.schemas import RuleEvaluation


def evaluate_rules(command: str) -> RuleEvaluation:
    paths = extract_paths(command)
    black_dirs = find_black_directories(paths)
    white_cmd = is_white_command(command)
    black_cmd = is_black_command(command)
    white_only = only_white_directories(paths)

    if black_dirs:
        return RuleEvaluation(
            risk_level="red",
            reason=f"涉及黑目录: {', '.join(black_dirs)}",
            matched_white_command=white_cmd,
            matched_black_command=black_cmd,
            black_directories=black_dirs,
            white_directories_only=white_only,
            extracted_paths=paths,
        )

    if white_cmd:
        return RuleEvaluation(
            risk_level="green",
            reason="白命令且不涉及黑目录",
            matched_white_command=True,
            matched_black_command=black_cmd,
            white_directories_only=white_only,
            extracted_paths=paths,
        )

    if black_cmd:
        if white_only:
            return RuleEvaluation(
                risk_level="yellow",
                reason="黑命令但操作范围仅在白目录内",
                matched_black_command=True,
                white_directories_only=True,
                extracted_paths=paths,
            )
        return RuleEvaluation(
            risk_level="red",
            reason="黑命令且不限于白目录",
            matched_black_command=True,
            white_directories_only=False,
            extracted_paths=paths,
        )

    return RuleEvaluation(
        risk_level="yellow",
        reason="未命中白/黑命令规则，需模型判断",
        matched_white_command=white_cmd,
        matched_black_command=black_cmd,
        white_directories_only=white_only,
        extracted_paths=paths,
    )
