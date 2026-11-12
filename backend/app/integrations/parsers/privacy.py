import re


def redact(text: str) -> str:
    text = re.sub(r"(?:微信号|QQ号|联系地址|家庭住址|住址)[：:\s]*[^，,;；\s]+", "[contact]", text)
    text = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", "[identity]", text)
    text = re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "[phone]", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", text)
    text = re.sub(r"(?:sk-|Bearer\s+)[A-Za-z0-9_.-]{8,}", "[credential]", text, flags=re.I)
    return text


def unsafe_instruction(text: str) -> bool:
    return bool(
        re.search(
            r"忽略.{0,12}(?:规则|提示|指令)|系统提示|(?:api\s*key)|密钥|secret|执行\s*sql|drop\s+table|https?://",
            text,
            re.I,
        )
    )
