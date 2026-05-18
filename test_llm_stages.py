from llm_stages import generate_rmf_table

# Test input
# 测试输入
device_name = "Wearable Sepsis Biosensor"

intended_use = "monitor infection-related changes and support early sepsis detection"

device_type = "wearable biosensor"

# Generate RMF table
# 生成 RMF 表格
df, prompt, rag_context = generate_rmf_table(
    device_name,
    intended_use,
    device_type
)

print("===== Generated RMF Table =====")
print(df)

print("\n===== Prompt Preview =====")
print(prompt[:1000])

print("\n===== RAG Context =====")
print(rag_context)