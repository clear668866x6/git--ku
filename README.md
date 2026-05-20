# 编译原理课程设计 — 任务 3.2 (中间代码) & 4.2 (LLVM优化)

## 项目简介

| 任务 | 功能 |
|------|------|
| **3.2 中间代码** | 词法分析 → 语法分析(AST) → 语义分析(符号表) → 生成四元式 → 解释执行 |
| **4.2 LLVM** | 四元式 → LLVM IR → 编译执行(clang/lli) → 对比解释器结果 |

提供 Web 界面，可查看所有中间过程：Token序列、AST、符号表、四元式、LLVM IR。

---

## 环境配置

### Python 环境 (必须)
```bash
pip install flask
```

### LLVM (任务 4.2 需要)

**Linux (Ubuntu/Debian):**
```bash
sudo apt install llvm clang
```

**Windows:**
1. 下载 LLVM：https://github.com/llvm/llvm-project/releases
   - 选择 `LLVM-19.1.0-win64.exe` 或最新版本
2. 安装时勾选 "Add LLVM to the system PATH"
3. 重启终端，验证安装：`clang --version`

**macOS:**
```bash
brew install llvm
```

---

## 快速开始

### 1. 启动 Web 界面
```bash
cd compiler_web
python app.py
```
打开浏览器访问 **http://127.0.0.1:5000**

### 2. 手动运行 (命令行)

**任务 3.2：**
```bash
cd compiler_web
python -c "
from task32 import process_32
res = process_32('int main(void) { int a=10; write(a); return a; }', [])
print(res['output'])
print(res['quadruples'])
"
```

**任务 4.2 (四元式 → LLVM → 编译执行 → 对比)：**
```bash
cd compiler_web
python -c "
from task42 import process_42
res = process_42('int main(void) { int a=10; write(a); return a; }', [])
print('LLVM IR:')
print(res['llvm_ir'])
print('解释器输出:', res['interp_output'])
print('LLVM输出:', res['llvm_output'])
print('是否一致:', res['match'])
"
```

**任务 4.2 手动编译 LLVM IR：**
```bash
# 先获取 LLVM IR
python -c "
from task32 import process_32
from task42 import generate_llvm
res = process_32('int main(void) { int a=10; write(a); return a; }')
ir = generate_llvm(res['quads_list'], res['func_table'])
open('test.ll','w').write(ir)
"
# 编译 LLVM IR
clang -x ir test.ll -o test
# 运行
./test          # Linux/macOS
test.exe        # Windows
```

### 3. 批量生成 .int/.doc 文件
```bash
cd compiler_web
python generate_all.py
```
生成后查看 `test_results.txt` 了解所有测试通过情况。

---

## 文件结构

```
compiler_web/
├── app.py                  ← Flask Web 服务器
├── task32.py               ← 任务 3.2 全部代码
├── task42.py               ← 任务 4.2 全部代码
├── generate_all.py         ← 批量生成 .int/.doc + 测试结果
├── test_results.txt        ← 测试通过/失败汇总
├── README.md               ← 本文件
├── templates/
│   └── index.html          ← Web 前端
├── test_cases_32/          ← 3.2 测试用例 (42个 .txt)
├── test_cases_42/          ← 4.2 测试用例 (13个 .txt)
├── test_output_32/         ← 3.2 输出 (42 .int + 42 .doc)
└── test_output_42/         ← 4.2 输出 (13 .int + 13 .doc)
```

---

## 输出文件说明

### .int 文件 — 中间过程
- 3.2：Token序列 + AST + 符号表
- 4.2：Token序列 + AST + 符号表 + 四元式 + **LLVM IR**

### .doc 文件 — 结果
- 3.2：四元式 + 解释器输出
- 4.2：四元式 + 解释器输出 + LLVM编译输出 + **对比结果**

---

## 四元式格式

严格采用课程标准格式：
```
(运算符, 操作数1, 操作数2, 结果)

(J>=, i, 5, 11)     条件跳转: 如果 i>=5 则跳到第11行
(J, _, _, 5)         无条件跳转到第5行
(=, t0, _, n)        赋值: n = t0
(=[], arr, i, t1)    数组读取: t1 = arr[i]
([]=, t2, i, arr)    数组写入: arr[i] = t2
(read, _, _, t0)     读取输入
(write, x, _, _)     输出 x
(+, a, b, t0)        加法: t0 = a + b
(-, *, /, %, 同理)
(<, >, <=, >=, ==, !=)  比较运算
(&&, a, b, t0)       逻辑与: t0 = a && b
(||, a, b, t0)       逻辑或: t0 = a || b
(param, x, _, _)     函数参数压栈
(call, func, 2, t3)  调用函数 func, 2个参数, 结果→t3
(return, r, _, _)    返回 r
```

---

## 测试用例

### 3.2 (42个)
- test0.1 ~ test5.5：编译器课程全部原始测试用例 (39个)
- test_32_comprehensive1/2：2个综合测试
- test_32_error：1个错误用例

### 4.2 (13个)
- test1 ~ test10：10个示例 (算术/分支/循环/数组/函数/递归等)
- test_42_comprehensive1/2：2个综合测试
- test_42_error：1个错误用例

---

## 常见问题

**Q: 运行报错 "未找到LLVM工具链"？**
A: 安装 LLVM (见上方环境配置)。如已安装仍报错，检查 PATH 环境变量。

**Q: Windows 上 clang 编译报错？**
A: 确保 LLVM 安装目录的 `bin` 文件夹在 PATH 中。安装时勾选 "Add to PATH"。

**Q: 如何只运行 3.2 不跑 4.2？**
A: 在 Web 界面点击「任务 3.2」按钮，或用命令行调用 `process_32()`。

**Q: 四元式格式与老师要求不一致？**
A: 本实现的四元式格式与 `test_all_in_one.int` 完全一致，可对照验证。
