"""
Scrapy 크롤링 통계 확인 스크립트 / Script to check Scrapy crawling statistics
중복 제거 상태 결과 확인용 / Used to get deduplication check status results

기능 설명 / Features:
- 당일 및 과거 전체 논문 데이터 간의 중복 확인 / Check duplication between today's and all historical paper data
- 중복 논문 항목 제거 및 신규 논문 유지 / Remove duplicate papers, keep new content
- 중복 제거 결과에 따라 워크플로 계속 진행 여부 결정 / Decide workflow continuation based on deduplication results
"""
import glob
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


def normalize_id(paper_id: str) -> str:
    """Normalize paper ID or DOI for robust comparison."""
    if not paper_id:
        return ""
    pid = paper_id.strip().lower()
    pid = re.sub(r"^https?://(dx\.)?doi\.org/", "", pid)
    pid = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", pid)
    pid = re.sub(r"v\d+$", "", pid)
    return pid.strip()


def normalize_title(title: str) -> str:
    """Normalize paper title by removing punctuation and whitespace."""
    if not title:
        return ""
    clean = re.sub(r"<[^>]+>", "", title).lower()
    clean = re.sub(r"[^\w\s]", "", clean)
    return " ".join(clean.split())


def get_data_dir() -> Path:
    """Find the data directory reliably."""
    candidates = [
        Path("../data"),
        Path("data"),
        Path(__file__).resolve().parents[2] / "data",
    ]
    for d in candidates:
        if d.exists() and d.is_dir():
            return d
    return Path("../data")


def load_papers_data(file_path):
    """
    jsonl 파일에서 전체 논문 데이터 로드
    Load complete paper data from jsonl file
    
    Args:
        file_path (Path or str): JSONL 파일 경로 / JSONL file path
        
    Returns:
        list: 논문 데이터 목록 / List of paper data
        set: 정규화된 논문 ID 집합 / Set of normalized paper IDs
        set: 정규화된 논문 제목 집합 / Set of normalized paper titles
    """
    if not os.path.exists(file_path):
        return [], set(), set()
    
    papers = []
    ids = set()
    titles = set()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    papers.append(data)
                    pid = normalize_id(data.get("id", ""))
                    t = normalize_title(data.get("title", ""))
                    if pid:
                        ids.add(pid)
                    if t:
                        titles.add(t)
        return papers, ids, titles
    except (OSError, ValueError) as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return [], set(), set()


def save_papers_data(papers, file_path):
    """
    논문 데이터를 jsonl 파일로 저장
    Save paper data to jsonl file
    
    Args:
        papers (list): 논문 데이터 목록 / List of paper data
        file_path (Path or str): 파일 경로 / File path
    """
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(paper, ensure_ascii=False) + "\n" for paper in papers)
        return True
    except OSError as e:
        print(f"Error saving {file_path}: {e}", file=sys.stderr)
        return False


def perform_deduplication():
    """
    과거 전체 논문 및 당일 자체 중복 제거 수행: 과거 및 당일 중복 논문 항목 제거 및 신규 논문만 유지
    Perform deduplication over all past historical records and intra-day duplicates
    
    Returns:
        str: 중복 제거 상태 / Deduplication status
             - "has_new_content": 신규 내용 있음 / Has new content
             - "no_new_content": 신규 내용 없음 / No new content  
             - "no_data": 데이터 없음 / No data
             - "error": 처리 오류 / Processing error
    """
    data_dir = get_data_dir()
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    today_file = data_dir / f"{today}.jsonl"

    if not today_file.exists():
        print(f"오늘 데이터 파일이 존재하지 않습니다 ({today_file}) / Today's data file does not exist", file=sys.stderr)
        return "no_data"

    try:
        today_papers, _, _ = load_papers_data(today_file)
        print(f"오늘 수집된 원본 논문 수: {len(today_papers)} / Today's crawled papers: {len(today_papers)}", file=sys.stderr)

        if not today_papers:
            return "no_data"

        # 1. 과거 전체 날짜의 ID 및 Title 집합 수집
        history_ids = set()
        history_titles = set()
        historical_files = [
            f for f in data_dir.glob("*.jsonl")
            if not f.name.startswith(today) and "AI_enhanced" not in f.name
        ]

        for h_file in historical_files:
            _, past_ids, past_titles = load_papers_data(h_file)
            history_ids.update(past_ids)
            history_titles.update(past_titles)

        print(
            f"과거 전체 히스토리 중복 확인 DB 크기: {len(history_ids)}건 ID, {len(history_titles)}건 제목 (과거 파일 {len(historical_files)}개) / "
            f"Total history deduplication library size: {len(history_ids)} IDs, {len(history_titles)} titles ({len(historical_files)} files)",
            file=sys.stderr
        )

        # 2. 당일 논문 중 자체 중복 및 과거 히스토리 중복 필터링
        seen_today_ids = set()
        seen_today_titles = set()
        new_papers = []
        duplicate_count = 0

        for paper in today_papers:
            pid = normalize_id(paper.get("id", ""))
            t = normalize_title(paper.get("title", ""))

            # 과거 히스토리 또는 오늘 이미 추가된 것과 중복인지 확인
            is_dup = False
            if pid and (pid in history_ids or pid in seen_today_ids):
                is_dup = True
            elif t and (t in history_titles or t in seen_today_titles):
                is_dup = True

            if is_dup:
                duplicate_count += 1
                print(f"중복 논문 제외: {paper.get('id')} - {paper.get('title')[:40]}", file=sys.stderr)
            else:
                new_papers.append(paper)
                if pid:
                    seen_today_ids.add(pid)
                if t:
                    seen_today_titles.add(t)

        print(f"중복 논문 {duplicate_count}편 제거됨 / Removed {duplicate_count} duplicate papers", file=sys.stderr)
        print(f"중복 제거 후 남은 신규 논문 수: {len(new_papers)} / Remaining new papers: {len(new_papers)}", file=sys.stderr)

        if new_papers:
            if save_papers_data(new_papers, today_file):
                print(f"오늘 파일 업데이트 완료 / Today's file updated successfully: {today_file}", file=sys.stderr)
                return "has_new_content"
            else:
                print("중복 제거 데이터 저장 실패 / Failed to save deduplicated data", file=sys.stderr)
                return "error"
        else:
            try:
                today_file.unlink(missing_ok=True)
                print("모든 논문이 중복이므로 오늘 파일 삭제됨 / All papers are duplicates, today's file deleted", file=sys.stderr)
            except OSError as e:
                print(f"파일 삭제 실패: {e} / Failed to delete file: {e}", file=sys.stderr)
            return "no_new_content"

    except Exception as e:  # noqa: BLE001 - top-level guard, must return "error" not crash the workflow
        print(f"중복 제거 처리 실패: {e} / Deduplication processing failed: {e}", file=sys.stderr)
        return "error"


def main():
    """
    중복 제거 상태를 확인하고 해당 종료 코드 반환
    Check deduplication status and return corresponding exit code
    
    종료 코드 의미 / Exit code meanings:
    0: 신규 내용 있음, 처리 계속 / Has new content, continue processing
    1: 신규 내용 없음, 워크플로 중단 / No new content, stop workflow
    2: 처리 오류 / Processing error
    """
    print("중복 제거 확인 실행 중... / Performing intelligent deduplication check...", file=sys.stderr)
    
    dedup_status = perform_deduplication()
    
    if dedup_status == "has_new_content":
        print("✅ 중복 제거 완료, 신규 내용 발견, 워크플로 계속 진행 / Deduplication completed, new content found, continue workflow", file=sys.stderr)
        sys.exit(0)
    elif dedup_status == "no_new_content":
        print("⏹️ 중복 제거 완료, 신규 내용 없음, 워크플로 중단 / Deduplication completed, no new content, stop workflow", file=sys.stderr)
        sys.exit(1)
    elif dedup_status == "no_data":
        print("⏹️ 오늘 데이터 없음, 워크플로 중단 / No data today, stop workflow", file=sys.stderr)
        sys.exit(1)
    elif dedup_status == "error":
        print("❌ 중복 제거 처리 오류, 워크플로 중단 / Deduplication processing error, stop workflow", file=sys.stderr)
        sys.exit(2)
    else:
        print("❌ 알 수 없는 중복 제거 상태, 워크플로 중단 / Unknown deduplication status, stop workflow", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main() 