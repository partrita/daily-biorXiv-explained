import argparse
import json
import os
import re
from itertools import count
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, required=True, help="Path to the jsonline file")
    args = parser.parse_args()
    data = []
    preference = os.environ.get("CATEGORIES", "de novo design, antibody design").split(",")
    preference = [x.strip() for x in preference]

    def rank(cate):
        if cate in preference:
            return preference.index(cate)
        else:
            return len(preference)

    with open(args.data, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))

    categories = {item["categories"][0] for item in data} if data else set()
    template_path = Path(__file__).resolve().parent / "paper_template.md"
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    categories = sorted(categories, key=rank)
    cnt = {cate: 0 for cate in categories}
    for item in data:
        if item["categories"][0] not in cnt:
            continue
        cnt[item["categories"][0]] += 1

    markdown = "<div id=toc></div>\n\n# Table of Contents\n\n"
    for idx, cate in enumerate(categories):
        markdown += f"- [{cate}](#{cate}) [Total: {cnt[cate]}]\n"

    idx = count(1)
    for cate in categories:
        markdown += f"\n\n<div id='{cate}'></div>\n\n"
        markdown += f"# {cate} [[Back]](#toc)\n\n"
        papers = []
        for item in data:
            if item["categories"][0] == cate:
                # Safely access AI fields with default values
                ai_data = item.get("AI", {})
                if not ai_data or not isinstance(ai_data, dict):
                    print(f"Skipping item '{item.get('title', 'Unknown')}' due to missing or invalid AI data")
                    continue

                # Check if all required AI fields are present
                required_fields = ["tldr", "motivation", "method", "result", "conclusion"]
                if not all(field in ai_data for field in required_fields):
                    print(f"Skipping item '{item.get('title', 'Unknown')}' due to incomplete AI fields")
                    continue

                papers.append(
                    template.format(
                        title=item["title"],
                        authors=",".join(item.get("authors", [])),
                        summary=item.get("summary", ""),
                        url=item.get("abs", ""),
                        tldr=ai_data.get("tldr", ""),
                        motivation=ai_data.get("motivation", ""),
                        method=ai_data.get("method", ""),
                        result=ai_data.get("result", ""),
                        conclusion=ai_data.get("conclusion", ""),
                        cate=item["categories"][0],
                        idx=next(idx),
                    )
                )
        markdown += "\n\n".join(papers)

    # Calculate output markdown path (e.g., data/2026-09-18_AI_enhanced_Korean.jsonl -> data/2026-09-18.md)
    output_md = re.sub(r"_AI_enhanced_.*\.jsonl$", ".md", args.data)
    if output_md == args.data:
        output_md = str(Path(args.data).with_suffix(".md"))

    with open(output_md, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"Markdown generated: {output_md}")