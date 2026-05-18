from retrieval import build_rag_context

# Example input
# 示例输入
device_name = "Wearable sepsis biosensor"
intended_use = "monitor patient infection risk and support early sepsis detection"
device_type = "wearable biosensor"

# Build RAG context
# 构建 RAG 上下文
context = build_rag_context(device_name, intended_use, device_type)

print("===== ISO 14971 Notes =====")
print(context["iso14971_notes"])

print("\n===== Relevant Risk Cases =====")
print(context["relevant_cases"])