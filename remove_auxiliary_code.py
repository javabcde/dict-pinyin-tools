import os
import re

# 设置dicts文件夹路径（固定路径，后续可在此处修改）
dicts_folder = r"D:\RimeConfig\rime-wanxiang-yx-fuzhu\dicts"

# 确保dicts文件夹存在
if not os.path.exists(dicts_folder):
    print(f"错误：找不到dicts文件夹：{dicts_folder}")
    exit(1)

print(f"正在处理文件夹：{dicts_folder}")

# 获取dicts文件夹下所有.dict.yaml文件
dict_files = [f for f in os.listdir(dicts_folder) if f.endswith('.dict.yaml')]

if not dict_files:
    print("没有找到.dict.yaml文件")
    exit(0)

print(f"找到{len(dict_files)}个.dict.yaml文件需要处理：")
for file in dict_files:
    print(f"  - {file}")

# 处理每个.dict.yaml文件
for dict_file in dict_files:
    file_path = os.path.join(dicts_folder, dict_file)
    
    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 处理文件内容
    lines = content.split('\n')
    processed_lines = []
    
    # 用于判断是否在元数据部分
    in_metadata = False
    
    for line in lines:
        # 处理元数据开始标记
        if line.strip() == '---':
            in_metadata = True
            processed_lines.append(line)
            continue
        
        # 处理元数据结束标记
        if line.strip() == '...':
            in_metadata = False
            processed_lines.append(line)
            continue
        
        # 保留元数据部分不处理
        if in_metadata:
            processed_lines.append(line)
            continue
        
        # 保留注释行不处理
        if line.strip().startswith('#'):
            processed_lines.append(line)
            continue
        
        # 处理词典内容行
        # 分割行内容，使用Tab作为分隔符
        parts = line.split('\t')
        if len(parts) >= 2:
            # 处理拼音部分，去掉辅助码
            # 先按空格分割多个拼音
            pinyins = parts[1].split()
            # 对每个拼音单独处理，去除辅助码
            processed_pinyins = []
            for pinyin in pinyins:
                # 分割拼音和辅助码
                pinyin_parts = pinyin.split(';')
                if pinyin_parts:
                    processed_pinyins.append(pinyin_parts[0])  # 只保留分号前的部分
            # 重新组合拼音部分
            parts[1] = ' '.join(processed_pinyins)
            
            # 重新组合行内容
            processed_line = '\t'.join(parts)
            processed_lines.append(processed_line)
        else:
            # 如果行格式不符合预期，保留原始行
            processed_lines.append(line)
    
    # 写回处理后的内容
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(processed_lines))
    
    print(f"已处理文件：{dict_file}")

print("所有文件处理完成！")