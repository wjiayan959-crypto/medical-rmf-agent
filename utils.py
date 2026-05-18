import pandas as pd  # 数据表处理


RISK_TABLE_COLUMNS = [
    "Hazard",
    "Hazardous Situation",
    "Possible Harm",
    "Severity",
    "Probability",
    "Initial Risk Level",
    "Risk Control Measure",
    "Residual Risk",
    "Verification Method",
    "Status"
]
# RMF标准列结构（和ISO14971对齐）


def empty_risk_table():
    # 创建一个空表（后面LLM填充）
    # Create empty RMF table

    return pd.DataFrame(columns=RISK_TABLE_COLUMNS)


def validate_device_input(device_name, intended_use, device_type):
    # 输入校验（防止空值）
    # Validate user input

    errors = []

    if not device_name.strip():
        errors.append("Device name is required.")  # 设备名不能为空

    if not intended_use.strip():
        errors.append("Intended use is required.")

    if not device_type.strip():
        errors.append("Device type is required.")

    return errors