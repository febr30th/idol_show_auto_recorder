from settings import load_settings
from live48_scraper import fetch_shows_and_members
from feishu_bitable import FeishuBitableClient


def should_exclude_show(show_name: str, keywords: list[str]) -> bool:
    """公演名中包含任一排除关键词，则返回 True"""
    for kw in keywords:
        if kw and kw in show_name:
            return True
    return False


def dash_to_slash(date_dash: str) -> str:
    return date_dash.replace("-", "/")


def is_blank_record(fields: dict, field_date: str, field_content: str) -> bool:
    # 空行/无效：日期+行程内容都空（即使场次计数有值也算空行）
    def empty(v):
        return v is None or str(v).strip() == ""
    return empty(fields.get(field_date)) and empty(fields.get(field_content))


def is_valid_record(fields: dict, field_date: str, field_content: str) -> bool:
    # 有效：日期或行程内容任一非空
    def nonempty(v):
        return v is not None and str(v).strip() != ""
    return nonempty(fields.get(field_date)) or nonempty(fields.get(field_content))


def prepare_table_state(records: list, field_date: str, field_content: str, field_count: str) -> dict:
    """
    全表一次扫描，得到：
    - exists_set：用于全表去重的 (日期, 行程内容) 集合
    - next_count：最后有效记录的场次计数 + 1（有效但计数非法 -> 抛异常）
    - blank_ids：最后有效记录之后的所有空行 record_id（用于连续覆盖）
    """
    exists_set = set()
    last_valid_idx = None
    last_valid_count = None

    # 1) 扫描全表：去重集合 + 最后有效行
    for i, rec in enumerate(records):
        fields = rec.get("fields", {}) or {}

        d = fields.get(field_date)
        c = fields.get(field_content)
        if d is not None and c is not None:
            if str(d).strip() != "" and str(c).strip() != "":
                exists_set.add((str(d), str(c)))

        if is_valid_record(fields, field_date, field_content):
            last_valid_idx = i

            # 有效记录但场次计数非法 -> 直接抛异常（避免计数错乱）
            raw = fields.get(field_count)
            if raw is None or str(raw).strip() == "":
                raise RuntimeError(f"数据错误：发现有效记录但场次计数为空。记录索引={i}, fields={fields}")
            s = str(raw).strip()
            if not s.isdigit():
                raise RuntimeError(f"数据错误：发现有效记录但场次计数不是纯数字。值={raw}, 记录索引={i}, fields={fields}")

            last_valid_count = int(s)

    if last_valid_count is None:
        raise RuntimeError("未能在全表中找到任何有效记录及其合法的场次计数。")

    next_count = last_valid_count + 1

    # 2) 收集最后有效记录之后的所有空行 record_id（用于连续覆盖）
    blank_ids = []
    if last_valid_idx is not None:
        for j in range(last_valid_idx + 1, len(records)):
            fields = records[j].get("fields", {}) or {}
            if is_blank_record(fields, field_date, field_content):
                rid = records[j].get("record_id") or records[j].get("id")
                if rid:
                    blank_ids.append(rid)

    return {"exists_set": exists_set, "next_count": next_count, "blank_ids": blank_ids}


def run():
    # 每次执行都重新读取配置：方便你修改 settings.json / settings.local.json 后无需重启托盘
    cfg = load_settings()

    LIVE48_URLS = list(cfg["live48"]["urls"])
    TARGET_NAME = str(cfg["target"]["name"])
    EXCLUDE_SHOW_NAME_KEYWORDS = list(cfg["live48"].get("exclude_show_name_keywords", []))

    FIELD_COUNT = str(cfg["fields"]["count"])
    FIELD_DATE = str(cfg["fields"]["date"])
    FIELD_CONTENT = str(cfg["fields"]["content"])
    FIELD_REMARK = str(cfg["fields"]["remark"])

    target_shows = []
    for live48_url in LIVE48_URLS:
        shows = fetch_shows_and_members(live48_url)
        if not shows:
            continue

        for info in shows:
            show_name = str(info.get("show_name", ""))
            dt = str(info.get("datetime", ""))
            members = list(info.get("members") or [])

            if should_exclude_show(show_name, EXCLUDE_SHOW_NAME_KEYWORDS):
                print("排除公演（命中关键词）：", show_name)
                continue

            print(show_name, dt)
            # print(members)

            if TARGET_NAME in members:
                target_shows.append(info)

    if not target_shows:
        print(f"今日所有公演均未出现 {TARGET_NAME}，结束。")
        return

    feishu_cfg = cfg["feishu"]
    client = FeishuBitableClient(
        app_id=str(feishu_cfg["app_id"]),
        app_secret=str(feishu_cfg["app_secret"]),
        bitable_app_token=str(feishu_cfg["bitable_app_token"]),
        bitable_table_id=str(feishu_cfg["bitable_table_id"]),
    )

    # ✅ 全表读取一次（注意：这会分页拉完整张表）
    records = client.get_records_in_order()

    state = prepare_table_state(
        records=records,
        field_date=FIELD_DATE,
        field_content=FIELD_CONTENT,
        field_count=FIELD_COUNT,
    )

    exists_set = state["exists_set"]
    next_count = state["next_count"]
    blank_ids = state["blank_ids"]

    for info in target_shows:
        show_name = str(info.get("show_name", ""))
        date_slash = dash_to_slash(str(info.get("date_dash", "")))
        dt = str(info.get("datetime", ""))
        content = f"{show_name}（{dt}）"

        # ✅ 全表级去重
        if (date_slash, content) in exists_set:
            print("已存在同记录，跳过：", date_slash, content)
            continue

        new_fields = {
            FIELD_COUNT: str(next_count),  # 多行文本必须字符串
            FIELD_DATE: date_slash,
            FIELD_CONTENT: content,
            FIELD_REMARK: "自动记录-含" + TARGET_NAME,
        }

        if blank_ids:
            rid = blank_ids.pop(0)
            client.update_record(rid, new_fields)
            print("覆盖空行成功 record_id:", rid, "场次计数:", next_count)
        else:
            result = client.create_record(new_fields)
            rid = result.get("data", {}).get("record", {}).get("record_id")
            print("新建成功 record_id:", rid, "场次计数:", next_count)

        # ✅ 更新去重集合，避免同次运行重复写入
        exists_set.add((date_slash, content))
        next_count += 1


if __name__ == "__main__":
    run()
