import glob
import json
import os
import re
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import scrapy


def normalize_id(paper_id: str) -> str:
    """Normalize paper ID or DOI for robust comparison."""
    if not paper_id:
        return ""
    pid = paper_id.strip().lower()
    pid = re.sub(r"^https?://(dx\.)?doi\.org/", "", pid)
    pid = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", pid)
    pid = re.sub(r"v\d+$", "", pid)  # Remove version suffix like v1, v2
    return pid.strip()


def normalize_title(title: str) -> str:
    """Normalize paper title by removing punctuation and whitespace."""
    if not title:
        return ""
    clean = re.sub(r"<[^>]+>", "", title).lower()
    clean = re.sub(r"[^\w\s]", "", clean)
    return " ".join(clean.split())


class ArxivSpider(scrapy.Spider):
    name = "arxiv"
    allowed_domains: ClassVar[list[str]] = ["biorxiv.org", "ebi.ac.uk", "arxiv.org"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        raw_query = os.environ.get("SEARCH_QUERY", "") or os.environ.get("CATEGORIES", "de novo design")
        queries = [q.strip() for q in raw_query.split(",") if q.strip()]
        self.search_queries = queries if queries else ["de novo design"]

        # 무료 Quota 절약을 위해 날짜 범위를 최근 2~3일로 엄격히 제한
        now = datetime.now(UTC)
        self.end_date = now.strftime("%Y-%m-%d")
        days_back = int(os.environ.get("DAYS_BACK", "3"))
        self.start_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
        self.max_papers_per_query = int(os.environ.get("MAX_PAPERS", "5"))

        # 과거 및 런타임 중복 체크를 위한 세트 초기화
        self.seen_ids: set[str] = set()
        self.seen_titles: set[str] = set()
        self._load_existing_papers()

        self.logger.info(
            f"bioRxiv 검색 시작 - 키워드: {self.search_queries}, "
            f"기간: {self.start_date} ~ {self.end_date}, 키워드당 최대: {self.max_papers_per_query}건 "
            f"(기존 중복 방지 DB: {len(self.seen_ids)}건 ID, {len(self.seen_titles)}건 제목)"
        )

    def _load_existing_papers(self):
        """과거 수집된 모든 jsonl 파일에서 이미 존재하는 논문 ID 및 제목 로드"""
        data_dirs = [
            Path("../data"),
            Path("data"),
            Path(__file__).resolve().parents[3] / "data",
        ]
        target_dir = None
        for d in data_dirs:
            if d.exists() and d.is_dir():
                target_dir = d
                break

        if not target_dir:
            return

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        for file_path in target_dir.glob("*.jsonl"):
            # 당일 생성된 파일이 아닌 과거 파일만 로드
            if file_path.name.startswith(today):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            pid = normalize_id(data.get("id", ""))
                            title = normalize_title(data.get("title", ""))
                            if pid:
                                self.seen_ids.add(pid)
                            if title:
                                self.seen_titles.add(title)
            except Exception as e:
                self.logger.warning(f"기존 데이터 로드 실패 ({file_path}): {e}")

    def start_requests(self):
        for query in self.search_queries:
            # 최근 날짜 범위(FIRST_PDATE)로 필터링하여 오래된 논문 대량 수집 방지
            epmc_query = f"(\"{query}\") AND (PUBLISHER:bioRxiv OR SRC:PPR) AND FIRST_PDATE:[{self.start_date} TO {self.end_date}]"
            url = (
                f"https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                f"?query={urllib.parse.quote(epmc_query)}"
                f"&resultType=core&format=json&pageSize={self.max_papers_per_query}&sort=P_PDATE_D%20desc"
            )
            yield scrapy.Request(
                url=url,
                callback=self.parse_epmc_json,
                headers={"User-Agent": "daily-arxiv-ai-enhanced/1.0"},
                meta={"query": query},
                dont_filter=True,
            )

    def parse_epmc_json(self, response):
        query = response.meta.get("query", "de novo design")
        try:
            data = json.loads(response.text)
        except ValueError as e:
            self.logger.error(f"JSON 파싱 실패 ({response.url}): {e}")
            return

        results = data.get("resultList", {}).get("result", [])
        self.logger.info(f"bioRxiv 검색어 '{query}' ({self.start_date} ~ {self.end_date}) 결과: {len(results)}건 발견")

        for r in results[: self.max_papers_per_query]:
            doi = r.get("doi", "")
            title = r.get("title", "")
            title = re.sub(r"<[^>]+>", "", title).strip().rstrip(".")
            abstract = r.get("abstractText", "")
            abstract = re.sub(r"<[^>]+>", "", abstract).strip()

            if not title or not abstract:
                continue

            paper_id = doi or r.get("id", "")
            norm_id = normalize_id(paper_id)
            norm_title = normalize_title(title)

            # 중복 확인: ID 또는 제목이 이미 존재하는 경우 건너뜀
            if norm_id and norm_id in self.seen_ids:
                self.logger.info(f"중복 논문 건너뜀 (ID 중복): {paper_id} - {title[:40]}")
                continue
            if norm_title and norm_title in self.seen_titles:
                self.logger.info(f"중복 논문 건너뜀 (제목 중복): {title[:40]}")
                continue

            # 신규 논문 기록
            if norm_id:
                self.seen_ids.add(norm_id)
            if norm_title:
                self.seen_titles.add(norm_title)

            authors = [
                a.get("fullName")
                for a in r.get("authorList", {}).get("author", [])
                if a.get("fullName")
            ]
            if not authors and r.get("authorString"):
                authors = [a.strip() for a in r.get("authorString").split(",") if a.strip()]

            pub_date = r.get("firstPublicationDate") or r.get("dateOfCreation") or ""

            if doi:
                abs_url = f"https://www.biorxiv.org/content/{doi}v1"
                pdf_url = f"https://www.biorxiv.org/content/{doi}v1.full.pdf"
            else:
                full_urls = r.get("fullTextUrlList", {}).get("fullTextUrl", [])
                abs_url = full_urls[0].get("url", "") if full_urls else ""
                pdf_url = abs_url

            yield {
                "id": paper_id,
                "title": title,
                "authors": authors,
                "categories": ["bioRxiv", query],
                "comment": f"bioRxiv preprint ({pub_date})" if pub_date else "bioRxiv preprint",
                "summary": abstract,
                "abs": abs_url,
                "pdf": pdf_url,
            }
