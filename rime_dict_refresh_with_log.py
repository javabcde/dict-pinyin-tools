#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rime 词典刷新与辅助码管理工具（带日志）
功能：先移除词典中的辅助码，再刷新拼音和添加新的易学码辅助码，并记录详细操作日志
注意：本工具会直接修改源文件，请确保提前备份重要数据！
"""

import os, re, shutil, tempfile, sys, logging, datetime
from typing import Dict, List, Optional

# 设置日志记录配置
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"rime_dict_refresh_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('rime_dict_refresh')

# 检查必要的依赖包
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    logger.warning("未安装tqdm包，进度条功能不可用")
    HAS_TQDM = False

try:
    from pypinyin import pinyin, Style, load_phrases_dict, load_single_dict
    HAS_PYPINYIN = True
except ImportError:
    logger.error("未安装pypinyin包，无法进行拼音处理")
    HAS_PYPINYIN = False

# ─────────────── 配 置 区 ────────────────
INPUT_PATH  = r"E:\RimeConfig\rime-wanxiang-yx-fuzhu\dicts"  # 目录或单文件路径
REFRESH_PINYIN = True          # 是否刷新拼音
REFRESH_AUX_CODE = True        # 是否刷新辅助码
AUX_FILE    = r"e:\RimeConfig\dict-pinyin-tools\auxcode\手心辅易学码9.txt"  # 辅助码文件路径
CUSTOM_PINYIN_DIR = r"e:\RimeConfig\dict-pinyin-tools\pinyin_data"  # 自定义拼音数据目录
AUX_SEP_REGEX = r'[;\[]'       # 定义“拼音后缀”分隔符；默认匹配 `;` 与 `[`
# ──────────────────────────────────────

# 表头定义
yaml_heads = ('---', 'name:', 'version:', 'sort:', '...')
skip_set = {
    "compatible.dict.yaml", "corrections.dict.yaml",
    "chars.dict.yaml", "people.dict.yaml", "encnnum.dict.yaml"
}

# ---------- 加载自定义拼音 ----------
def load_custom_pinyin_from_directory(directory: str):
    s_map, p_map = {}, {}
    if not os.path.isdir(directory):
        logger.warning(f"自定义拼音目录不存在: {directory}")
        return
    try:
        for fn in os.listdir(directory):
            if not fn.endswith(('.txt', '.yaml')):
                continue
            file_path = os.path.join(directory, fn)
            try:
                with open(file_path, encoding='utf-8') as f:
                    for line in f:
                        word, *py = line.rstrip('\n').split('\t')
                        if not py:
                            continue
                        plist = py[0].split()
                        if len(word) == 1:
                            s_map[ord(word)] = ','.join(plist)
                        else:
                            p_map[word] = [[p] for p in plist]
            except UnicodeDecodeError:
                logger.warning(f"无法解码文件 {file_path}，尝试其他编码...")
                # 尝试使用其他常见编码
                for encoding in ['gbk', 'latin-1']:
                    try:
                        with open(file_path, encoding=encoding) as f:
                            for line in f:
                                word, *py = line.rstrip('\n').split('\t')
                                if not py:
                                    continue
                                plist = py[0].split()
                                if len(word) == 1:
                                    s_map[ord(word)] = ','.join(plist)
                                else:
                                    p_map[word] = [[p] for p in plist]
                        break
                    except UnicodeDecodeError:
                        continue
    except Exception as e:
        logger.error(f"加载自定义拼音时出错: {e}")
        return
    
    if p_map:
        load_phrases_dict(p_map)
        logger.info(f"✓ 词组拼音加载 {len(p_map)} 条")
    if s_map:
        load_single_dict(s_map)
        logger.info(f"✓ 单字拼音加载 {len(s_map)} 条")

# ---------- 加载辅助码映射 ----------
def load_aux_metadata(path: str) -> Dict[str, str]:
    aux_map: Dict[str, str] = {}
    if not os.path.exists(path):
        logger.warning(f"辅助码文件不存在: {path}")
        return aux_map
    
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if not line.strip() or line.startswith('#'):
                    continue
                
                # 尝试多种分隔符解析：先尝试制表符分割，再尝试等号分割
                if '\t' in line:
                    parts = line.rstrip('\n').split('\t')
                elif '=' in line:
                    parts = line.rstrip('\n').split('=')
                else:
                    # 如果没有找到制表符或等号，跳过此行
                    continue
                
                # 确保分割后有两部分，且第一部分是单个字符
                if len(parts) < 2 or len(parts[0]) != 1:
                    continue
                
                char = parts[0].strip()
                seg_full = parts[1].strip()
                
                # 解析辅助码（如果辅助码部分包含分隔符）
                seg_parts = re.split(AUX_SEP_REGEX, seg_full, maxsplit=1)
                if len(seg_parts) > 1:
                    aux_map[char] = seg_parts[1].strip()
                else:
                    aux_map[char] = seg_full.strip()
                
                # 修正：如果辅助码仅为 ; 或为空，设为空
                if aux_map[char] == ';' or not aux_map[char]:
                    aux_map[char] = ''
    except Exception as e:
        logger.error(f"加载辅助码时出错: {e}")
        return aux_map
    
    logger.info(f"✓ 辅助码加载 {len(aux_map)} 条")
    return aux_map

# ---------- 类型识别 ----------
def is_userdb_head(line: str) -> bool:
    return '#@/db_type\tuserdb' in line or '# Rime user dictionary' in line

# ---------- 拼音处理函数 ----------
def tone_mark(seg: str) -> str:
    """seg = 'bin;sc' → 'bīn;sc'（仅根拼音加调）"""
    if not HAS_PYPINYIN:
        return seg
    
    root   = re.split(AUX_SEP_REGEX, seg)[0]
    suffix = seg[len(root):]
    py = pinyin(root, style=Style.TONE, heteronym=False, errors='ignore')
    return (py[0][0] if py else root) + suffix

# ---------- 辅助码处理函数 ----------
def build_seg_by_aux(word: str, aux_map: Dict[str, str]) -> List[str]:
    return [aux_map.get(ch, '') for ch in word]

# ---------- 移除辅助码函数 ----------
def remove_auxiliary_code_from_line(line: str, userdb: bool) -> str:
    """从行中移除辅助码"""
    cols = line.split('\t')
    
    # 确定拼音部分的索引
    if userdb and len(cols) >= 1:
        # 用户词典格式：拼音段(含后缀)\t汉字\t...
        pinyin_index = 0
    elif not userdb and len(cols) >= 2:
        # 普通词典格式：汉字\t拼音\t...
        pinyin_index = 1
    else:
        return line  # 格式不符合，返回原行
    
    # 处理拼音部分，去掉辅助码
    pinyins = cols[pinyin_index].split()
    processed_pinyins = []
    for pinyin_part in pinyins:
        # 分割拼音和辅助码
        pinyin_parts = pinyin_part.split(';')
        if pinyin_parts:
            processed_pinyins.append(pinyin_parts[0])  # 只保留分号前的部分
    
    # 重新组合拼音部分
    cols[pinyin_index] = ' '.join(processed_pinyins)
    
    # 重新组合行内容
    return '\t'.join(cols)

# ---------- 安全地读取文件内容 ----------
def read_file_safely(file_path: str) -> Optional[List[str]]:
    """尝试使用多种编码安全地读取文件内容"""
    encodings = ['utf-8', 'gbk', 'latin-1']
    for encoding in encodings:
        try:
            with open(file_path, encoding=encoding) as f:
                return [line.rstrip('\n') for line in f]
        except UnicodeDecodeError:
            continue
    logger.error(f"无法解码文件 {file_path}，请检查文件编码")
    return None

# ---------- 移除文件中的辅助码 ----------
def remove_auxiliary_code_in_file(file_path: str):
    # 跳过不需要处理的文件
    if os.path.basename(file_path) in skip_set:
        logger.info(f"  跳过文件: {os.path.basename(file_path)}")
        return False
    
    # 检查文件是否可写
    if not os.access(file_path, os.W_OK):
        logger.error(f"没有写入权限: {os.path.basename(file_path)}")
        return False
    
    userdb = False
    processed_lines = []
    modified = False
    lines_removed_aux = 0
    
    # 1. 先将文件全部读入内存
    lines = read_file_safely(file_path)
    if lines is None:
        return False
    
    for line in lines:
        # 处理表头和注释行
        if line.startswith(yaml_heads) or line.startswith('#'):
            processed_lines.append(line)
            if is_userdb_head(line):
                userdb = True
            continue
        
        # 处理空行
        if not line.strip():
            processed_lines.append('')
            continue
        
        # 尝试移除辅助码
        new_line = remove_auxiliary_code_from_line(line, userdb)
        if new_line != line:
            modified = True
            lines_removed_aux += 1
        processed_lines.append(new_line)
    
    if not modified:
        logger.info(f"  未发现需要移除辅助码的内容: {os.path.basename(file_path)}")
        return True
    
    # 2. 使用临时文件写入，然后原子性替换原文件
    temp_dir = os.path.dirname(file_path)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False,
                                         dir=temp_dir, suffix='.tmp') as tmp:
            tmp.write('\n'.join(processed_lines) + '\n')
            temp_path = tmp.name
        
        # 原子性替换文件
        try:
            # 在Windows系统上，需要先删除目标文件
            if os.path.exists(file_path):
                os.unlink(file_path)
            shutil.move(temp_path, file_path)
            logger.info(f"✓ 已移除文件中的辅助码: {os.path.basename(file_path)} (修改行数: {lines_removed_aux})")
            return True
        except Exception as e:
            logger.error(f"替换文件失败: {e}")
            # 清理临时文件
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            return False
    except Exception as e:
        logger.error(f"写入临时文件时出错: {e}")
        # 清理临时文件
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        return False

# ---------- 原地处理单个文件（刷新拼音和添加辅助码） ----------
def process_file_in_place(file_path: str, aux_map: Dict[str, str]):
    # 跳过不需要处理的文件
    if os.path.basename(file_path) in skip_set:
        logger.info(f"  跳过文件: {os.path.basename(file_path)}")
        return False
    
    # 检查文件是否可写
    if not os.access(file_path, os.W_OK):
        logger.error(f"没有写入权限: {os.path.basename(file_path)}")
        return False
    
    userdb = False
    processed_lines = []
    modified = False
    lines_refreshed_pinyin = 0
    lines_refreshed_aux = 0
    
    # 1. 先将文件全部读入内存
    lines = read_file_safely(file_path)
    if lines is None:
        return False
    
    for line in lines:
        # 处理表头和注释行
        if line.startswith(yaml_heads) or line.startswith('#'):
            processed_lines.append(line)
            if is_userdb_head(line):
                userdb = True
            continue
        
        # 处理空行
        if not line.strip():
            processed_lines.append('')
            continue
        
        # 处理数据行
        cols = line.split('\t')
        original_line = '\t'.join(cols)
        
        # 安全地获取汉字部分
        try:
            word = cols[1] if userdb else cols[0]
            if not word.strip():
                processed_lines.append(line)  # 跳过空的汉字部分
                continue
        except IndexError:
            logger.warning(f"无效的行格式: {line[:50]}...")
            processed_lines.append(line)
            continue
        
        # 刷新拼音
        if REFRESH_PINYIN and HAS_PYPINYIN:
            try:
                if userdb and len(cols) >= 3:
                    # 用户词典格式：拼音段(含后缀)\t汉字\t...
                    segs = cols[0].split() if cols else []
                    # 确保word不为空，且为非空字符串
                    if not word.strip():
                        processed_lines.append(line)
                        continue
                    
                    char_py = [p[0] for p in pinyin(word, style=Style.TONE, heteronym=False)]
                    
                    new_segs = []
                    for i, seg in enumerate(segs):
                        base_py = char_py[i] if i < len(char_py) else tone_mark(seg)
                        root = re.split(AUX_SEP_REGEX, seg)[0]
                        suffix = seg[len(root):]
                        new_segs.append(base_py + suffix)
                    
                    cols[0] = ' '.join(new_segs)
                else:
                    # 普通词典格式：汉字\t拼音\t...
                    # 确保word不为空，且为非空字符串
                    if not word.strip():
                        processed_lines.append(line)
                        continue
                    
                    char_py = [p[0] for p in pinyin(word, style=Style.TONE, heteronym=False)]
                    
                    if len(cols) == 1:  # 仅汉字
                        cols.append(' '.join(char_py))
                    elif len(cols) >= 2 and cols[1].isdigit():  # 词 + 词频
                        cols = [word, ' '.join(char_py)] + cols[1:]
                    elif len(cols) >= 2:
                        # 有原拼音列，需要保留后缀
                        segs = cols[1].split()
                        new_segs = []
                        for i, py in enumerate(char_py):
                            if i < len(segs):
                                root = re.split(AUX_SEP_REGEX, segs[i])[0]
                                suffix = segs[i][len(root):]
                            else:
                                suffix = ''
                            new_segs.append(py + suffix)
                        cols[1] = ' '.join(new_segs)
                lines_refreshed_pinyin += 1
            except Exception as e:
                logger.warning(f"处理拼音时出错: {e}，跳过该行拼音刷新")
        
        # 刷新辅助码
        if REFRESH_AUX_CODE and aux_map:
            try:
                seg_idx = 0 if userdb else 1
                if not userdb and len(cols) == 1:
                    cols.insert(1, '')
                elif userdb and len(cols) < 2:
                    cols.append('')
                
                # 安全地访问列
                if seg_idx < len(cols):
                    raw_segs = cols[seg_idx].strip().split()
                else:
                    raw_segs = []
                    if userdb:
                        cols.insert(0, '')
                    else:
                        cols.insert(1, '')
                
                aux_segs = build_seg_by_aux(word, aux_map)
                
                merged = []
                for i, py in enumerate(raw_segs):
                    aux = aux_segs[i] if i < len(aux_segs) else ''
                    # 如果py已经包含辅助码，先移除
                    root = re.split(AUX_SEP_REGEX, py)[0]
                    merged.append(f"{root};{aux}")
                
                if userdb:
                    cols[0] = ' '.join(merged)
                else:
                    # 确保merged不为空
                    if merged:
                        cols[seg_idx] = ' '.join(merged)
                lines_refreshed_aux += 1
            except Exception as e:
                logger.warning(f"处理辅助码时出错: {e}，跳过该行辅助码刷新")
        
        # 处理userdb格式的特殊要求
        if userdb and cols and len(cols) > 0:
            # 如果是userdb行且首列没空格，就补1个空格
            if not cols[0].endswith(' '):
                cols[0] += ' '
        
        # 检查行是否被修改
        processed_line = '\t'.join(cols)
        if processed_line != original_line:
            modified = True
        
        # 将处理后的行添加到结果中
        processed_lines.append(processed_line)
    
    if not modified:
        logger.info(f"  未发现需要刷新的内容: {os.path.basename(file_path)}")
        return True
    
    # 2. 使用临时文件写入，然后原子性替换原文件
    temp_dir = os.path.dirname(file_path)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False,
                                         dir=temp_dir, suffix='.tmp') as tmp:
            tmp.write('\n'.join(processed_lines) + '\n')
            temp_path = tmp.name
        
        # 原子性替换文件
        try:
            # 在Windows系统上，需要先删除目标文件
            if os.path.exists(file_path):
                os.unlink(file_path)
            shutil.move(temp_path, file_path)
            logger.info(f"✓ 已刷新文件: {os.path.basename(file_path)} (拼音行数: {lines_refreshed_pinyin}, 辅助码行数: {lines_refreshed_aux})")
            return True
        except Exception as e:
            logger.error(f"替换文件失败: {e}")
            # 清理临时文件
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            return False
    except Exception as e:
        logger.error(f"写入临时文件时出错: {e}")
        # 清理临时文件
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        return False

# ---------- 批量移除辅助码 ----------
def batch_remove_auxiliary_code(path: str):
    logger.info(f"===== 开始批量移除辅助码 =====")
    
    # 如果是单文件
    if os.path.isfile(path):
        remove_auxiliary_code_in_file(path)
        return
    
    # 如果是目录，递归处理所有文件
    tasks = []
    for root, _dirs, files in os.walk(path):
        for fn in files:
            if fn.endswith(('.txt', '.yaml')):
                tasks.append(os.path.join(root, fn))
    
    if not tasks:
        logger.warning(f"在路径 {path} 中未找到需要处理的文件")
        return
    
    logger.info(f"找到 {len(tasks)} 个文件需要处理")
    
    if HAS_TQDM:
        bar = tqdm(tasks, desc="移除辅助码", unit="file", ncols=90)
        success_count = 0
        for file_path in bar:
            bar.set_postfix(file=os.path.basename(file_path))
            if remove_auxiliary_code_in_file(file_path):
                success_count += 1
        logger.info(f"移除辅助码完成: 成功 {success_count}/{len(tasks)}")
    else:
        # 如果没有tqdm包，使用普通循环
        success_count = 0
        for file_path in tasks:
            logger.info(f"处理文件: {os.path.basename(file_path)}")
            if remove_auxiliary_code_in_file(file_path):
                success_count += 1
        logger.info(f"移除辅助码完成: 成功 {success_count}/{len(tasks)}")

# ---------- 批量处理文件或目录（刷新拼音和辅助码） ----------
def batch_refresh_dict_files(path: str, aux_map: Dict[str, str]):
    logger.info(f"===== 开始批量刷新词典文件 =====")
    
    # 如果是单文件
    if os.path.isfile(path):
        process_file_in_place(path, aux_map)
        return
    
    # 如果是目录，递归处理所有文件
    tasks = []
    for root, _dirs, files in os.walk(path):
        for fn in files:
            if fn.endswith(('.txt', '.yaml')):
                tasks.append(os.path.join(root, fn))
    
    if not tasks:
        logger.warning(f"在路径 {path} 中未找到需要处理的文件")
        return
    
    logger.info(f"找到 {len(tasks)} 个文件需要处理")
    
    if HAS_TQDM:
        bar = tqdm(tasks, desc="刷新词典", unit="file", ncols=90)
        success_count = 0
        for file_path in bar:
            bar.set_postfix(file=os.path.basename(file_path))
            if process_file_in_place(file_path, aux_map):
                success_count += 1
        logger.info(f"刷新词典完成: 成功 {success_count}/{len(tasks)}")
    else:
        # 如果没有tqdm包，使用普通循环
        success_count = 0
        for file_path in tasks:
            logger.info(f"处理文件: {os.path.basename(file_path)}")
            if process_file_in_place(file_path, aux_map):
                success_count += 1
        logger.info(f"刷新词典完成: 成功 {success_count}/{len(tasks)}")

# ---------- 主入口 ----------
if __name__ == "__main__":
    logger.info("Rime 词典刷新与辅助码管理工具（带日志）启动...")
    logger.info(f"日志文件已保存至: {log_file}")
    logger.warning("⚠️ 警告：本工具会直接修改源文件，请确保已备份重要数据！")
    
    # 检查是否需要拼音处理但缺少必要依赖
    if REFRESH_PINYIN and not HAS_PYPINYIN:
        logger.error("需要进行拼音处理，但未找到pypinyin包")
        logger.error("请安装pypinyin包: pip install pypinyin")
        sys.exit(1)
    
    try:
        # 检查输入路径是否存在
        if not os.path.exists(INPUT_PATH):
            logger.error(f"输入路径不存在: {INPUT_PATH}")
            logger.error("请修改配置区中的 INPUT_PATH 参数指向有效的文件或目录")
            sys.exit(1)
        
        # 第一步：移除词典中的辅助码
        batch_remove_auxiliary_code(INPUT_PATH)
        
        # 第二步：加载自定义拼音（如果需要）
        if REFRESH_PINYIN and CUSTOM_PINYIN_DIR and HAS_PYPINYIN:
            load_custom_pinyin_from_directory(CUSTOM_PINYIN_DIR)
        
        # 第三步：加载辅助码（如果需要）
        aux_map = load_aux_metadata(AUX_FILE) if REFRESH_AUX_CODE else {}
        
        # 第四步：刷新拼音和添加新的辅助码
        batch_refresh_dict_files(INPUT_PATH, aux_map)
        
    except KeyboardInterrupt:
        logger.info("\n[INFO] 用户中断了处理过程")
    except Exception as e:
        logger.error(f"处理过程中出现未预期的错误: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        logger.info("===== 处理流程完成 =====")
        logger.info(f"详细日志已保存至: {log_file}")
        logger.info("注意：请检查处理结果是否符合预期。建议定期备份词典文件。")