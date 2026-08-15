; python.scm — 危险 Python 模式（S-expression 查询，零正则）
;
; 捕获名语义（由 ast_guard.py 声明表校验，见 EXPECTED_CAPTURES）:
;   @fn_exec  — 直接代码执行类（eval/exec/compile/动态导入/交互输入）
;   @fn_sys   — 系统访问类（命令执行/反序列化/动态库加载）
;   @imp_dyn  — 动态导入危险模块
;   @alias_exec — 内建函数别名（getattr(__builtins__, 'eval') 形态）
;   @sub_exec  — 内建下标调用（__builtins__['eval'](...) 形态）
;
; 模式 1: 直接代码执行函数（identifier 调用）
(call function: (identifier) @fn_exec
  (#match? @fn_exec "^(eval|exec|compile|__import__|input|globals|locals)$"))

; 模式 2: 危险模块方法调用（object.method 形态）
(call function: (attribute
    object: (identifier) @obj
    attribute: (identifier) @meth) @fn_sys
  (#match? @obj "^(os|subprocess|commands|pickle|yaml|shelve|ctypes|pty|telnetlib|ftplib|socket)$")
  (#match? @meth "^(system|popen|Popen|run|call|check_call|check_output|getoutput|getstatusoutput|loads|load|CDLL|WinDLL|open|spawn|sendall|connect)$"))

; 模式 3: 动态导入（importlib / __import__ 别名）
(call function: (attribute
    object: (identifier) @obj
    attribute: (identifier) @meth) @imp_dyn
  (#eq? @obj "importlib")
  (#any-of? @meth "import_module" "reload"))

; ── 模式 4/5: 批判审计 (2026-08-04) 补漏 —— 别名/下标形态绕过 ────────────
; 实证: eval(user_input) 以裸 identifier 出现时被模式 1 阻断, 但
;   fn = getattr(__builtins__, 'eval'); fn(x)  以及  __builtins__['eval'](x)
; 均绕过模式 1-3 (ast_guard 只看函数名, 不看别名绑定/数据流)。
; 诚实边界: 字符串拼接形态 getattr(__builtins__, 'ev'+'al') /
;   __builtins__['e'+'val'] 的静态值不可判定 (binary_operator), 属
;   documented bypass —— 需数据流/常量折叠分析, 超出 tree-sitter 模式能力。
;
; 模式 4: 内建别名 —— getattr(__builtins__|builtins, 'eval'|'exec'|...)
(call function: (identifier) @fn_getattr
  (#eq? @fn_getattr "getattr")
  (argument_list
    (identifier) @builtins_target
    (string) @alias_attr)
  (#match? @builtins_target "^(__builtins__|__builtin__|builtins)$")
  (#match? @alias_attr "(eval|exec|compile|__import__|input)")) @alias_exec

; 模式 5: 内建下标调用 —— __builtins__['eval'](...)
(call function: (subscript
    (identifier) @builtins_sub
    (string) @sub_idx) @sub_exec
  (#match? @builtins_sub "^(__builtins__|__builtin__|builtins)$")
  (#match? @sub_idx "['\"](eval|exec|compile|__import__|input)['\"]"))
