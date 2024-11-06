from datetime import timedelta

from tqdm import tqdm

from prediction_market_agent_tooling.tools.tavily.tavily_search import tavily_search
from scripts.adhoc.deprecated_tavily_storage import (
    TAVILY_STORAGE,
    Session,
    TavilyResponseModel,
    select,
)


def main() -> None:
    failed = 0
    total = 0

    with Session(TAVILY_STORAGE.engine) as session:
        sql_query = select(TavilyResponseModel)
        for item in tqdm(session.exec(sql_query)):
            total += 1
            try:
                news_since = (
                    None
                    if item.days is None
                    else (item.datetime_.date() - timedelta(item.days))
                )
                tavily_search(
                    item.query,
                    item.search_depth,
                    item.topic,
                    news_since,
                    item.max_results,
                    item.include_domains,
                    item.exclude_domains,
                    item.include_answer,
                    item.include_raw_content,
                    item.include_images,
                    item.use_cache,
                    old_created_at=item.datetime_,  # Pass the original row creation datetime into tthe cache, so we don't accidentally treat all the old results as being made on day of running this script.
                )
            except Exception as e:
                failed += 1
                print(f"Failed to migrate {item.query}; {total=} {failed=}")

    print(f"{total=} {failed=}")


if __name__ == "__main__":
    main()
