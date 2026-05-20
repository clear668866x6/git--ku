from flask import Flask, render_template, request, jsonify
import os
import glob
from task32 import process_32
from task42 import process_42, find_llvm_tool

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST32_DIR = os.path.join(BASE_DIR, 'test_cases_32')
TEST42_DIR = os.path.join(BASE_DIR, 'test_cases_42')
OUT32_DIR = os.path.join(BASE_DIR, 'test_output_32')
OUT42_DIR = os.path.join(BASE_DIR, 'test_output_42')


def get_test_list(test_dir):
    files = sorted(glob.glob(os.path.join(test_dir, '*.txt')))
    result = []
    for fp in files:
        name = os.path.basename(fp).replace('.txt', '')
        content = ''
        for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']:
            try:
                with open(fp, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeError:
                continue
        result.append({'name': name, 'content': content})
    return result


@app.route('/', methods=['GET'])
def index():
    tests32 = get_test_list(TEST32_DIR)
    tests42 = get_test_list(TEST42_DIR)
    return render_template('index.html', tests32=tests32, tests42=tests42)


@app.route('/run32', methods=['POST'])
def run_32():
    code = request.form.get('code', '')
    inputs_str = request.form.get('inputs', '')
    inputs = []
    if inputs_str.strip():
        try:
            inputs = [int(x.strip()) for x in inputs_str.split(',') if x.strip()]
        except ValueError:
            pass
    res = process_32(code, inputs)
    return jsonify(res)


@app.route('/run42', methods=['POST'])
def run_42():
    code = request.form.get('code', '')
    inputs_str = request.form.get('inputs', '')
    inputs = []
    if inputs_str.strip():
        try:
            inputs = [int(x.strip()) for x in inputs_str.split(',') if x.strip()]
        except ValueError:
            pass
    res = process_42(code, inputs)
    return jsonify(res)


@app.route('/runall', methods=['POST'])
def run_all():
    code = request.form.get('code', '')
    inputs_str = request.form.get('inputs', '')
    inputs = []
    if inputs_str.strip():
        try:
            inputs = [int(x.strip()) for x in inputs_str.split(',') if x.strip()]
        except ValueError:
            pass
    res32 = process_32(code, inputs)
    if 'error' in res32:
        return jsonify({'error': res32['error']})
    res42 = process_42(code, inputs)
    return jsonify({
        'task32': {k: v for k, v in res32.items() if k not in ('quads_list', 'func_table')},
        'task42': {k: v for k, v in res42.items() if k not in ('quads_list', 'quadruples')}
    })


@app.route('/llvm_status', methods=['GET'])
def llvm_status():
    clang = find_llvm_tool('clang')
    lli = find_llvm_tool('lli')
    return jsonify({
        'clang': clang or '未找到',
        'lli': lli or '未找到',
        'os': os.name,
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
