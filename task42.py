import re
import subprocess
import os
import tempfile
import shutil
import sys

def parse_quadruples(text):
    quads = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ':' in line:
            line = line.split(':', 1)[1].strip()
        m = re.match(r'\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)', line)
        if m:
            op, a1, a2, a3 = m.group(1).strip(), m.group(2).strip(), m.group(3).strip(), m.group(4).strip()
            quads.append((op, a1, a2, a3))
    return quads


def generate_llvm_for_function(quads, func_name, params, inputs, global_input_size):
    """Generate LLVM for a single function given its quads."""
    lines = []

    # Find leaders (basic block starts)
    leaders = {0}
    for i, (op, a1, a2, res) in enumerate(quads):
        if op == 'J' or (op.startswith('J') and len(op) > 1):
            try:
                t = int(res)
                if 0 <= t < len(quads):
                    leaders.add(t)
            except ValueError:
                pass
            if i + 1 < len(quads):
                leaders.add(i + 1)
    leaders = sorted(leaders)

    block_of = {}
    for idx, l in enumerate(leaders):
        block_of[l] = f"block{idx}"

    # Collect variables
    all_vars = set()
    arr_vars = set()
    for op, a1, a2, res in quads:
        for a in [a1, a2, res]:
            if a and a != '_' and not a.isdigit() and not a.startswith('t'):
                all_vars.add(a)
    for op, a1, a2, res in quads:
        if op == '[]=':
            arr_vars.add(res)
        elif op == '=[]':
            arr_vars.add(a1)

    param_str = ', '.join(f'i32 %{p}' for p in params)
    lines.append(f'define i32 @{func_name}({param_str}) {{')
    lines.append('entry:')

    for v in sorted(all_vars):
        if v in arr_vars:
            lines.append(f'  %{v}_ptr = alloca [100 x i32]')
        else:
            lines.append(f'  %{v}_ptr = alloca i32')

    for p in params:
        lines.append(f'  store i32 %{p}, ptr %{p}_ptr')

    first_block = block_of[0]
    lines.append(f'  br label %{first_block}')
    lines.append('')

    tmp_cnt = 0

    def new_tmp():
        nonlocal tmp_cnt
        v = f"%rt{tmp_cnt}"
        tmp_cnt += 1
        return v

    def get_val(arg, blk):
        nonlocal tmp_cnt
        arg = arg.strip()
        if arg == '_':
            return None
        if arg.isdigit() or (arg.startswith('-') and arg[1:].isdigit()):
            return arg
        if arg.startswith('t'):
            return f'%{arg}'
        if arg in arr_vars:
            t = new_tmp()
            blk.append(f'  {t} = ptrtoint ptr %{arg}_ptr to i32')
            return t
        t = new_tmp()
        blk.append(f'  {t} = load i32, ptr %{arg}_ptr')
        return t

    param_stack = []

    for li in range(len(leaders)):
        bs = leaders[li]
        be = leaders[li + 1] if li + 1 < len(leaders) else len(quads)
        bname = block_of[bs]
        blk = [f'{bname}:']

        for qi in range(bs, be):
            op, a1, a2, res = quads[qi]

            if op == '=':
                v = get_val(a1, blk)
                blk.append(f'  store i32 {v}, ptr %{res}_ptr')

            elif op in ('+', '-', '*', '/', '%'):
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                ll_op = {'+': 'add', '-': 'sub', '*': 'mul', '/': 'sdiv', '%': 'srem'}[op]
                blk.append(f'  %{res} = {ll_op} i32 {v1}, {v2}')

            elif op in ('<', '>', '<=', '>=', '==', '!='):
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                ll_c = {'<': 'slt', '>': 'sgt', '<=': 'sle', '>=': 'sge',
                        '==': 'eq', '!=': 'ne'}[op]
                blk.append(f'  %{res}_i1 = icmp {ll_c} i32 {v1}, {v2}')
                blk.append(f'  %{res} = zext i1 %{res}_i1 to i32')

            elif op == '&&':
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                blk.append(f'  %{res}_c1 = icmp ne i32 {v1}, 0')
                blk.append(f'  %{res}_c2 = icmp ne i32 {v2}, 0')
                blk.append(f'  %{res}_b = and i1 %{res}_c1, %{res}_c2')
                blk.append(f'  %{res} = zext i1 %{res}_b to i32')

            elif op == '||':
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                blk.append(f'  %{res}_c1 = icmp ne i32 {v1}, 0')
                blk.append(f'  %{res}_c2 = icmp ne i32 {v2}, 0')
                blk.append(f'  %{res}_b = or i1 %{res}_c1, %{res}_c2')
                blk.append(f'  %{res} = zext i1 %{res}_b to i32')

            elif op == 'read':
                if inputs:
                    blk.append(f'  %ld_{qi} = load i32, ptr @input_idx')
                    blk.append(f'  %gp_{qi} = getelementptr [{global_input_size} x i32], ptr @input_data, i32 0, i32 %ld_{qi}')
                    blk.append(f'  %{res} = load i32, ptr %gp_{qi}')
                    blk.append(f'  %ni_{qi} = add i32 %ld_{qi}, 1')
                    blk.append(f'  store i32 %ni_{qi}, ptr @input_idx')
                else:
                    blk.append(f'  %{res} = add i32 0, 0')

            elif op == 'write':
                v = get_val(a1, blk)
                blk.append(f'  call i32 (ptr, ...) @printf(ptr @.fmt_num, i32 {v})')

            elif op == '=[]':
                idx = get_val(a2, blk)
                blk.append(f'  %gp_{res} = getelementptr [100 x i32], ptr %{a1}_ptr, i32 0, i32 {idx}')
                blk.append(f'  %{res} = load i32, ptr %gp_{res}')

            elif op == '[]=':
                v = get_val(a1, blk)
                idx = get_val(a2, blk)
                blk.append(f'  %gp_{qi} = getelementptr [100 x i32], ptr %{res}_ptr, i32 0, i32 {idx}')
                blk.append(f'  store i32 {v}, ptr %gp_{qi}')

            elif op == 'param':
                v = get_val(a1, blk)
                param_stack.append(v)

            elif op == 'call':
                func_name = a1
                num_args = int(a2)
                call_args = param_stack[-num_args:] if num_args > 0 else []
                param_stack = param_stack[:-num_args] if num_args > 0 else param_stack
                blk.append(f'  %{res} = call i32 @{func_name}({", ".join(f"i32 {a}" for a in call_args)})')

            elif op == 'return':
                v = get_val(a1, blk)
                blk.append(f'  ret i32 {v if v else "0"}')

            elif op == 'J':
                target_rel = int(res)
                blk.append(f'  br label %{block_of[target_rel]}')

            elif op.startswith('J') and len(op) > 1:
                rop = op[1:]
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                ll_c = {'<': 'slt', '>': 'sgt', '<=': 'sle', '>=': 'sge',
                        '==': 'eq', '!=': 'ne'}[rop]
                target_rel = int(res)
                next_qi = qi + 1
                next_name = block_of[next_qi] if next_qi in block_of else block_of[0]
                blk.append(f'  %brc_{qi} = icmp {ll_c} i32 {v1}, {v2}')
                blk.append(f'  br i1 %brc_{qi}, label %{block_of[target_rel]}, label %{next_name}')

        if not any(blk[-1].strip().startswith(s) for s in ['br ', 'ret ']):
            next_qi = be
            if next_qi in block_of:
                blk.append(f'  br label %{block_of[next_qi]}')
            else:
                blk.append('  ret i32 0')

        lines.extend(blk)
        lines.append('')

    lines.append('}')
    return '\n'.join(lines)


def generate_llvm(quads, func_table, inputs=None):
    """Generate complete LLVM module from quads and function table."""
    mod = []
    mod.append('declare i32 @printf(ptr, ...)')
    mod.append('')
    mod.append('@.fmt_num = private constant [4 x i8] c"%d\\0A\\00"')
    mod.append('')

    if inputs:
        n = len(inputs)
        vals = ', '.join(f'i32 {v}' for v in inputs)
        mod.append(f'@input_data = global [{n} x i32] [{vals}]')
        mod.append('@input_idx = global i32 0')
        global_input_size = n
    else:
        global_input_size = 0
    mod.append('')

    if not func_table:
        func_table = {'main': {'params': [], 'entry': 0}}

    # Determine function ranges from func_table
    entries = [(name, info['entry']) for name, info in func_table.items() if info.get('entry') is not None]
    entries.sort(key=lambda x: x[1])

    func_ranges = {}
    for idx in range(len(entries)):
        name, start = entries[idx]
        if idx + 1 < len(entries):
            end = entries[idx + 1][1]
        else:
            end = len(quads)
        # Convert absolute jump targets to relative within function
        fquads = []
        for q in quads[start:end]:
            op, a1, a2, res = q
            if op == 'J' or (op.startswith('J') and len(op) > 1):
                try:
                    target = int(res)
                    if start <= target < end:
                        res = str(target - start)
                except ValueError:
                    pass
            fquads.append((op, a1, a2, res))
        func_ranges[name] = {
            'quads': fquads,
            'params': func_table[name].get('params', [])
        }

    for name in [e[0] for e in entries]:
        finfo = func_ranges[name]
        fn_ll = generate_llvm_for_function(finfo['quads'], name, finfo['params'], inputs, global_input_size)
        mod.append(fn_ll)
        mod.append('')

    return '\n'.join(mod)


def find_llvm_tool(name):
    """Find LLVM tool (lli or clang) on Linux/Windows/macOS."""
    import shutil

    # Try PATH search first (works on all platforms)
    path = shutil.which(name)
    if path:
        return path

    if os.name == 'nt':
        exe_name = name + '.exe'
        # Try PATH with .exe suffix
        path = shutil.which(exe_name)
        if path:
            return path
        # Try common LLVM install locations on Windows
        for base in [
            r'C:\Program Files\LLVM\bin',
            r'C:\Program Files (x86)\LLVM\bin',
            r'C:\LLVM\bin',
            os.path.expandvars(r'%LOCALAPPDATA%\LLVM\bin'),
            os.path.expandvars(r'%APPDATA%\LLVM\bin'),
        ]:
            full = os.path.join(base, exe_name)
            if os.path.isfile(full):
                return full
        # Try running 'where' command as last resort
        try:
            result = subprocess.run(['where', exe_name], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split('\n')[0].strip()
        except Exception:
            pass

    return None


def compile_and_run(llvm_ir, inputs):
    """Compile LLVM IR with clang, then run. Falls back to lli if clang unavailable."""
    import uuid

    # First try clang (proper compilation)
    clang = find_llvm_tool('clang')
    if clang:
        try:
            base = os.path.join(tempfile.gettempdir(), f'llvm_{uuid.uuid4().hex[:8]}')
            ll_path = base + '.ll'
            exe_path = base + ('.exe' if os.name == 'nt' else '')
            with open(ll_path, 'w') as f:
                f.write(llvm_ir)
            try:
                compile_res = subprocess.run(
                    [clang, '-x', 'ir', ll_path, '-o', exe_path, '-Wno-override-module'],
                    capture_output=True, text=True, timeout=20
                )
                if compile_res.returncode != 0:
                    raise Exception(f'clang编译失败: {compile_res.stderr[:200]}')
                run_res = subprocess.run(
                    [exe_path],
                    capture_output=True, text=True, timeout=10,
                    input='' if not inputs else '\n'.join(str(x) for x in inputs)
                )
                return run_res.stdout.strip(), run_res.returncode, 'clang'
            finally:
                for f in [ll_path, exe_path]:
                    try:
                        os.unlink(f)
                    except OSError:
                        pass
        except Exception as e:
            pass  # fall back to lli

    # Fall back to lli (LLVM interpreter, no linking needed)
    lli = find_llvm_tool('lli')
    if lli:
        try:
            with tempfile.NamedTemporaryFile(suffix='.ll', mode='w', delete=False) as f:
                f.write(llvm_ir)
                temp_path = f.name
            try:
                run_res = subprocess.run(
                    [lli, temp_path],
                    capture_output=True, text=True, timeout=10
                )
                return run_res.stdout.strip(), run_res.returncode, 'lli'
            finally:
                os.unlink(temp_path)
        except FileNotFoundError:
            raise Exception('未找到lli或clang。请安装LLVM: sudo apt install llvm (Linux) 或 https://llvm.org (Windows)')
    raise Exception('未找到LLVM工具链(lli/clang)。请安装LLVM。')


def process_42(source_code, inputs=None):
    from task32 import process_32 as run_32

    try:
        result_32 = run_32(source_code, inputs)
        if 'error' in result_32:
            return {'error': result_32['error']}

        quads = result_32['quads_list']
        func_table = result_32['func_table']
        interp_output = result_32['output'].strip()
        retval = result_32.get('retval', 0)

        llvm_ir = generate_llvm(quads, func_table, inputs)

        try:
            llvm_output, llvm_ret, method = compile_and_run(llvm_ir, inputs)
        except FileNotFoundError:
            llvm_output = "错误: 未安装LLVM (lli/clang)"
            llvm_ret = -1
            method = 'none'
        except subprocess.TimeoutExpired:
            llvm_output = "错误: LLVM执行超时"
            llvm_ret = -1
            method = 'none'
        except Exception as e:
            llvm_output = f"错误: {e}"
            llvm_ret = -1
            method = 'none'

        match = (interp_output == llvm_output and retval == llvm_ret)

        return {
            'tokens': result_32['tokens'],
            'ast': result_32['ast'],
            'symbol_table': result_32['symbol_table'],
            'llvm_ir': llvm_ir,
            'llvm_output': llvm_output,
            'llvm_retcode': llvm_ret,
            'llvm_method': method,
            'interp_output': interp_output,
            'interp_retval': retval,
            'match': match,
            'quadruples': result_32['quadruples'],
            'quads_list': quads,
        }
    except Exception as e:
        import traceback
        return {'error': str(e) + '\n' + traceback.format_exc()}


if __name__ == '__main__':
    code = '''int main(void) {
    int a = 10;
    int b = 20;
    int max;
    if (a > b) {
        max = a;
    } else {
        max = b;
    }
    write(max);
    return max;
}'''
    res = process_42(code, [])
    if res.get('error'):
        print('ERROR:', res['error'])
    else:
        print('LLVM IR:')
        print(res['llvm_ir'])
        print('--- Interp:', repr(res['interp_output']))
        print('--- LLVM:', repr(res['llvm_output']))
        print('--- Match:', res['match'])
