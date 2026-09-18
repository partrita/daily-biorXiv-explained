import re
import arxiv
from scrapy.exceptions import DropItem


def _normalize_id(paper_id: str) -> str:
    if not paper_id:
        return ""
    pid = paper_id.strip().lower()
    pid = re.sub(r"^https?://(dx\.)?doi\.org/", "", pid)
    pid = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", pid)
    pid = re.sub(r"v\d+$", "", pid)
    return pid.strip()


def _normalize_title(title: str) -> str:
    if not title:
        return ""
    clean = re.sub(r"<[^>]+>", "", title).lower()
    clean = re.sub(r"[^\w\s]", "", clean)
    return " ".join(clean.split())


class DailyArxivPipeline:
    def __init__(self):
        self.page_size = 100
        self.client = None
        self.seen_ids = set()
        self.seen_titles = set()

    def process_item(self, item: dict, spider):
        pid = _normalize_id(item.get("id", ""))
        title = _normalize_title(item.get("title", ""))

        if pid and pid in self.seen_ids:
            raise DropItem(f"Duplicate paper ID dropped in pipeline: {item.get('id')}")
        if title and title in self.seen_titles:
            raise DropItem(f"Duplicate paper title dropped in pipeline: {item.get('title')}")

        if pid:
            self.seen_ids.add(pid)
        if title:
            self.seen_titles.add(title)

        # 이미 필요한 필드(title, summary 등)가 채워져 있는 경우 그대로 반환
        if item.get("title") and item.get("summary"):
            if not item.get("pdf") and item.get("id"):
                item["pdf"] = f"https://arxiv.org/pdf/{item['id']}"
            if not item.get("abs") and item.get("id"):
                item["abs"] = f"https://arxiv.org/abs/{item['id']}"
            return item

        # arXiv ID만 제공된 레거시 크롤링의 경우에만 arxiv 클라이언트를 사용하여 메타데이터 조회
        if self.client is None:
            self.client = arxiv.Client(self.page_size)

        item["pdf"] = f"https://arxiv.org/pdf/{item['id']}"
        item["abs"] = f"https://arxiv.org/abs/{item['id']}"
        search = arxiv.Search(
            id_list=[item["id"]],
        )
        try:
            paper = next(self.client.results(search))
            item["authors"] = [a.name for a in paper.authors]
            item["title"] = paper.title
            item["categories"] = paper.categories
            item["comment"] = paper.comment
            item["summary"] = paper.summary
        except Exception as e:  # noqa: BLE001 - arxiv lib raises varied errors, item must still be returned
            spider.logger.warning(f"Failed to fetch metadata from arXiv API for {item['id']}: {e}")

        return item
