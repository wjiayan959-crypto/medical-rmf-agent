import json
from pathlib import Path

# Get current project folder
# 获取当前项目文件夹路径
BASE_DIR = Path(__file__).resolve().parent

# Define data file paths
# 定义数据文件路径
ISO_NOTES_PATH = BASE_DIR / "data" / "standards" / "iso14971_notes.txt"
RISK_CASES_PATH = BASE_DIR / "data" / "risk_cases.json"


def load_iso14971_notes():
    """
    Load ISO 14971 notes from txt file.
    读取 ISO14971 相关说明文本。
    """

    if not ISO_NOTES_PATH.exists():
        # If file does not exist, return empty text
        # 如果文件不存在，返回空文本
        return ""

    with open(ISO_NOTES_PATH, "r", encoding="utf-8") as file:
        # Read all text content
        # 读取全部文本内容
        return file.read()


def load_risk_cases():
    """
    Load example risk cases from JSON file.
    读取示例风险案例。
    """

    if not RISK_CASES_PATH.exists():
        # If file does not exist, return empty list
        # 如果文件不存在，返回空列表
        return []

    with open(RISK_CASES_PATH, "r", encoding="utf-8") as file:
        # Convert JSON file into Python list/dict
        # 把 JSON 文件转换成 Python 列表/字典
        return json.load(file)


def simple_keyword_match(user_input, case):
    """
    Check whether user input is related to one risk case.
    判断用户输入是否和某个风险案例相关。
    """

    user_input = user_input.lower()

    # Combine all text in one case
    # 把一个案例里的所有文字合并起来
    case_text = " ".join([
        str(case.get("device_type", "")),
        str(case.get("hazard", "")),
        str(case.get("hazardous_situation", "")),
        str(case.get("possible_harm", "")),
        str(case.get("suggested_control", ""))
    ]).lower()

    # Split user input into keywords
    # 把用户输入拆成关键词
    keywords = user_input.split()

    # Count how many keywords appear in the case text
    # 统计有多少关键词出现在案例文本中
    score = 0
    for keyword in keywords:
        if keyword in case_text:
            score += 1

    return score


def retrieve_relevant_cases(user_input, top_k=3):
    """
    Retrieve the most relevant risk cases based on user input.
    根据用户输入检索最相关的风险案例。
    """

    risk_cases = load_risk_cases()

    scored_cases = []

    for case in risk_cases:
        # Calculate relevance score
        # 计算相关性分数
        score = simple_keyword_match(user_input, case)

        if score > 0:
            scored_cases.append((score, case))

    # Sort cases by score from high to low
    # 按相关性分数从高到低排序
    scored_cases.sort(key=lambda x: x[0], reverse=True)

    # Return top k cases only
    # 只返回最相关的前几个案例
    return [case for score, case in scored_cases[:top_k]]


def build_rag_context(device_name, intended_use, device_type):
    """
    Build RAG context for later LLM generation.
    为后续 LLM 生成内容构建上下文。
    """

    # Load standard notes
    # 读取标准说明
    iso_notes = load_iso14971_notes()

    # Combine user input into one query
    # 把用户输入合并成一个检索问题
    query = f"{device_name} {intended_use} {device_type}"

    # Retrieve relevant cases
    # 检索相关案例
    relevant_cases = retrieve_relevant_cases(query)

    context = {
        "iso14971_notes": iso_notes,
        "relevant_cases": relevant_cases
    }

    return context