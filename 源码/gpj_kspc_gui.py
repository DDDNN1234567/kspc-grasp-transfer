# -*- coding: utf-8 -*-
"""竞驰管家婆一键资料互传 —— 图形界面

源：竞驰管理通账套（T_base_wldw_inner / t_base_goods_inner 等）
目标：管家婆辉煌 TOP15 账套（走官方存储过程，编号与层级由管家婆维护）
"""
import os
import sys
import threading
import traceback
import tkinter as tk
from tkinter import ttk, messagebox

APP_TITLE = "竞驰管家婆一键资料互传 v1.2"
APP_VER = "1.2"

_BASE = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

import gpj_top15_core as core
import gpj_kspc_adapter as kspc

SRC_DST_MAP = [
    ("往来单位", "T_base_wldw_inner"),
    ("仓库", "t_base_storage_inner"),
    ("职员", "t_base_employees"),
    ("商品明细", "t_base_goods_inner"),
    ("库存结存", "t_base_goodsstock"),
    ("价格跟踪", "t_base_price"),
    ("条码", "t_base_GoodsBar"),
]
DST_TABLE_OF = {
    "往来单位": "btype",
    "仓库": "Stock",
    "职员": "employee",
    "商品明细": "ptype",
    "库存结存": "IniGoodsStocks",
    "价格跟踪": "xw_P_PriceFollow",
    "条码": "xw_PtypeBarCode",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1080x760")
        self.minsize(980, 660)
        self._busy = False
        self._build_style()
        self._build_header()
        self._build_tabs()
        self._build_footer()

    def _build_style(self):
        st = ttk.Style(self)
        for th in ("vista", "winnative", "clam"):
            if th in st.theme_names():
                try:
                    st.theme_use(th)
                    break
                except Exception:
                    continue
        st.configure("TNotebook.Tab", padding=(18, 8), font=("Microsoft YaHei", 10))
        st.configure("Run.TButton", font=("Microsoft YaHei", 11, "bold"), padding=(16, 8))
        st.configure("TButton", font=("Microsoft YaHei", 9), padding=(8, 5))
        st.configure("TLabel", font=("Microsoft YaHei", 9))
        st.configure("TEntry", padding=3)

    def _build_header(self):
        bar = tk.Frame(self, bg="#12355B", height=76)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="竞驰管家婆一键资料互传", bg="#12355B", fg="white",
                 font=("Microsoft YaHei", 19, "bold")).pack(side="left", padx=22)
        tk.Label(bar, text="竞驰管理通 → 管家婆辉煌 TOP15 · 官方过程通道 · v" + APP_VER,
                 bg="#12355B", fg="#A9C7E8", font=("Microsoft YaHei", 10)).pack(side="left", padx=8, pady=(8, 0))
        tk.Label(bar, text="往来单位 · 仓库 · 职员 · 商品 · 库存 · 价格 · 条码",
                 bg="#12355B", fg="#7FA8D4", font=("Microsoft YaHei", 9)).pack(side="right", padx=22)

    def _build_footer(self):
        f = tk.Frame(self, bg="#EEF3F9", height=30)
        f.pack(fill="x", side="bottom")
        f.pack_propagate(False)
        self.lbl_state = tk.Label(f, text="就绪", bg="#EEF3F9", fg="#33475B",
                                  font=("Microsoft YaHei", 9), anchor="w")
        self.lbl_state.pack(side="left", padx=14)
        tk.Label(f, text="导入前建议先备份目标账套基本资料 13 表", bg="#EEF3F9",
                 fg="#7A8899", font=("Microsoft YaHei", 9)).pack(side="right", padx=14)

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=10)
        self.tab_run = ttk.Frame(self.nb)
        self.tab_maint = ttk.Frame(self.nb)
        self.tab_help = ttk.Frame(self.nb)
        self.nb.add(self.tab_run, text="  一键导入  ")
        self.nb.add(self.tab_maint, text="  维护  ")
        self.nb.add(self.tab_help, text="  说明  ")
        self._build_run(self.tab_run)
        self._build_maint(self.tab_maint)
        self._build_help(self.tab_help)

    def _conn_frame(self, parent, title, hint, prefix):
        box = ttk.LabelFrame(parent, text=title)
        box.pack(fill="x", pady=(0, 8))
        g = ttk.Frame(box)
        g.pack(fill="x", padx=10, pady=8)
        vars_ = {}
        ttk.Label(g, text="实例").grid(row=0, column=0, sticky="w")
        vars_["server"] = tk.StringVar(value="")
        ttk.Entry(g, textvariable=vars_["server"], width=26).grid(row=0, column=1, padx=6, sticky="w")
        ttk.Label(g, text="库名").grid(row=0, column=2, sticky="w", padx=(14, 0))
        vars_["db"] = tk.StringVar(value="")
        cb = ttk.Combobox(g, textvariable=vars_["db"], width=16, state="normal")
        cb.grid(row=0, column=3, padx=6, sticky="w")
        vars_["db_combo"] = cb
        ttk.Label(g, text="sa 密码").grid(row=0, column=4, sticky="w", padx=(14, 0))
        vars_["pwd"] = tk.StringVar(value="")
        ttk.Entry(g, textvariable=vars_["pwd"], width=12, show="*").grid(row=0, column=5, padx=6, sticky="w")
        ttk.Button(g, text="测试连接", command=lambda p=prefix: self._test_conn(p)).grid(row=0, column=6, padx=(10, 2))
        ttk.Button(g, text="刷新库", command=lambda p=prefix: self._refresh_dbs(p)).grid(row=0, column=7)
        vars_["user"] = tk.StringVar(value="sa")
        lbl = ttk.Label(g, text=hint, foreground="#7A8899")
        lbl.grid(row=1, column=0, columnspan=8, sticky="w", pady=(6, 0))
        self.conn_vars[prefix] = vars_
        self.conn_lbl[prefix] = lbl

    conn_vars = {}
    conn_lbl = {}

    def _build_run(self, parent):
        pad = ttk.Frame(parent)
        pad.pack(fill="both", expand=True, padx=10, pady=8)
        self._conn_frame(pad, "① 源库 —— 竞驰管理通",
                         "读 T_base_wldw_inner / t_base_storage_inner / t_base_employees / t_base_goods_inner 等", "src")
        self._conn_frame(pad, "② 目标库 —— 管家婆辉煌 TOP15",
                         "写 btype / ptype / Stock / employee / IniGoodsStocks / xw_P_*", "dst")
        mid = ttk.Frame(pad)
        mid.pack(fill="x", pady=(2, 8))
        modbox = ttk.LabelFrame(mid, text="③ 导入模块")
        modbox.pack(side="left", fill="both", expand=True)
        grid = ttk.Frame(modbox)
        grid.pack(fill="x", padx=10, pady=8)
        self.mod_vars = {}
        for i, m in enumerate(kspc.MODULES):
            v = tk.BooleanVar(value=True)
            self.mod_vars[m] = v
            ttk.Checkbutton(grid, text=kspc.MODULE_CN.get(m, m), variable=v).grid(
                row=i // 3, column=i % 3, sticky="w", padx=6, pady=3)
        optbox = ttk.LabelFrame(mid, text="④ 选项")
        optbox.pack(side="left", fill="y", padx=(10, 0))
        self.var_incr = tk.BooleanVar(value=False)
        ttk.Checkbutton(optbox, text="增量模式（已存在的自定义编号跳过）",
                        variable=self.var_incr).pack(anchor="w", padx=10, pady=(10, 4))
        self.var_cache = tk.BooleanVar(value=True)
        ttk.Checkbutton(optbox, text="导入后清理客户端缓存",
                        variable=self.var_cache).pack(anchor="w", padx=10, pady=4)
        self.var_auto_bak = tk.BooleanVar(value=True)
        ttk.Checkbutton(optbox, text="导入前自动备份目标 13 表",
                        variable=self.var_auto_bak).pack(anchor="w", padx=10, pady=(4, 10))
        act = ttk.Frame(pad)
        act.pack(fill="x", pady=(0, 8))
        self.btn_run = ttk.Button(act, text="开始一键导入", style="Run.TButton", command=self._run_import)
        self.btn_run.pack(side="left")
        self.lbl_mods = ttk.Label(act, text="", foreground="#12355B")
        self.lbl_mods.pack(side="left", padx=14)
        logbox = ttk.LabelFrame(pad, text="⑤ 运行日志")
        logbox.pack(fill="both", expand=True)
        wrap = ttk.Frame(logbox)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt = tk.Text(wrap, height=12, wrap="word", font=("Consolas", 9),
                           bg="#0F1B26", fg="#D5E3EF", insertbackground="#D5E3EF")
        sb = ttk.Scrollbar(wrap, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)

    def _build_maint(self, parent):
        pad = ttk.Frame(parent)
        pad.pack(fill="both", expand=True, padx=10, pady=10)
        self._conn_frame(pad, "目标库 —— 管家婆辉煌 TOP15",
                         "备份 / 回滚 / 清缓存都在这里操作", "maint")
        box = ttk.LabelFrame(pad, text="维护操作")
        box.pack(fill="x", pady=(4, 10))
        row = ttk.Frame(box)
        row.pack(fill="x", padx=10, pady=10)
        ttk.Button(row, text="备份基本资料 13 表", command=self._do_backup).pack(side="left")
        ttk.Button(row, text="校验最近备份", command=self._do_verify).pack(side="left", padx=8)
        ttk.Button(row, text="回滚到最近备份", command=self._do_rollback).pack(side="left")
        ttk.Button(row, text="清理客户端缓存", command=self._do_clearcache).pack(side="left", padx=8)
        ttk.Button(row, text="检查更新", command=self._check_update).pack(side="left", padx=(16, 0))
        lst = ttk.LabelFrame(pad, text="已有备份前缀")
        lst.pack(fill="both", expand=True)
        wrap = ttk.Frame(lst)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.lst_pre = tk.Listbox(wrap, font=("Consolas", 9), height=10)
        sb2 = ttk.Scrollbar(wrap, command=self.lst_pre.yview)
        self.lst_pre.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self.lst_pre.pack(side="left", fill="both", expand=True)
        ttk.Button(lst, text="刷新列表", command=self._load_prefixes).pack(anchor="e", padx=10, pady=(0, 8))

    def _build_help(self, parent):
        t = tk.Text(parent, wrap="word", font=("Microsoft YaHei", 10),
                    bg="#FFFFFF", fg="#22303C", padx=18, pady=16)
        t.pack(fill="both", expand=True, padx=6, pady=6)
        t.insert("end", HELP_TEXT)
        t.configure(state="disabled")

    def _log(self, msg):
        self.txt.configure(state="normal")
        self.txt.insert("end", msg.rstrip() + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")
        self.lbl_state.configure(text=msg.strip()[:80])

    def _set_busy(self, busy):
        self._busy = busy
        self.btn_run.configure(state="disabled" if busy else "normal")

    def _conn_of(self, prefix):
        v = self.conn_vars[prefix]
        return v["server"].get().strip(), v["db"].get().strip(), v["user"].get().strip(), v["pwd"].get().strip()

    def _open(self, prefix):
        s, d, u, p = self._conn_of(prefix)
        if not (s and d and u):
            raise RuntimeError("请填写实例 / 库名 / 用户名")
        return core.connect(s, d, u, p, timeout=10)

    def _test_conn(self, prefix):
        def work():
            try:
                cn = self._open(prefix)
                cur = cn.cursor()
                if prefix == "src":
                    ok = kspc.is_kspc_database(cur)
                    ver = kspc.kspc_version(cur)
                    if ok:
                        txt = "✔ 竞驰账套已识别：ProductCode=%s 版本=%s 开账=%s 期间=%s" % ver
                    else:
                        txt = "✘ 未识别为竞驰账套（缺核心四表）"
                else:
                    cur.execute("SELECT COUNT(*) FROM sys.tables")
                    n = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM btype")
                    nb = cur.fetchone()[0]
                    txt = "✔ 管家婆账套可用：%d 张表，往来单位 %d 行" % (n, nb)
                self.conn_lbl[prefix].configure(text=txt)
                self._log(txt)
                cn.close()
            except Exception as e:
                self.conn_lbl[prefix].configure(text="✘ " + str(e)[:90])
                self._log("连接失败：" + str(e)[:160])
        threading.Thread(target=work, daemon=True).start()

    def _refresh_dbs(self, prefix):
        def work():
            try:
                s, _, u, p = self._conn_of(prefix)
                if not s:
                    raise RuntimeError("请先填实例名")
                dbs = core.list_databases(s, u, p, timeout=8)
                cb = self.conn_vars[prefix]["db_combo"]
                cb["values"] = dbs
                self.conn_lbl[prefix].configure(text="✔ 实例 %s 下共 %d 个库，已下拉可选" % (s, len(dbs)))
                self._log("已列出实例 %s 下 %d 个库" % (s, len(dbs)))
            except Exception as e:
                self.conn_lbl[prefix].configure(text="✘ 列库失败：" + str(e)[:80])
                self._log("列库失败：" + str(e)[:160])
        threading.Thread(target=work, daemon=True).start()

    def _run_import(self):
        if self._busy:
            messagebox.showwarning("请稍候", "已有任务正在执行。")
            return
        mods = [m for m, v in self.mod_vars.items() if v.get()]
        if not mods:
            messagebox.showwarning("未选模块", "请至少勾选一个导入模块。")
            return
        self._set_busy(True)
        threading.Thread(target=lambda: self._import_worker(mods), daemon=True).start()

    def _import_worker(self, mods):
        src = dst = None
        try:
            self._log("=" * 62)
            self._log("连接源库（竞驰）…")
            src = self._open("src")
            scur = src.cursor()
            if not kspc.is_kspc_database(scur):
                raise RuntimeError("源库不是竞驰账套（未找到 T_base_wldw_inner 等核心表）")
            self._log("  竞驰版本 " + " / ".join(kspc.kspc_version(scur)))
            self._log("连接目标库（管家婆）…")
            dst = self._open("dst")
            dcur = dst.cursor()
            self._log("快照源库行数…")
            src_counts = {}
            for cn_name, st in SRC_DST_MAP:
                try:
                    scur.execute("SET NOCOUNT ON; SELECT COUNT(*) FROM %s" % st)
                    src_counts[cn_name] = scur.fetchone()[0]
                except Exception:
                    src_counts[cn_name] = -1
            if self.var_auto_bak.get():
                self._log("备份目标 13 表…")
                pre = core.backup_tables(dcur)
                self._log("  已备份到 " + pre)
            self._log("开始导入，模块：%s" % "、".join(kspc.MODULE_CN.get(m, m) for m in mods))
            stat, errs = kspc.import_from_db(
                scur, dcur, modules=mods,
                logcb=lambda s: self._log("  " + str(s)),
                incremental=self.var_incr.get())
            self._log("-" * 62)
            self._log("导入结果：" + kspc.stats_text(stat))
            if errs:
                self._log("失败明细（共 %d 条）：" % len(errs))
                for e in errs[:40]:
                    self._log("  · " + e)
                if len(errs) > 40:
                    self._log("  … 其余 %d 条省略" % (len(errs) - 40))
            else:
                self._log("✔ 全部成功，无失败记录。")
            self._log("源-目标行数对照（验证日志）：")
            self._log("  %-10s %10s | %-18s %10s" % ("源(竞驰)", "源行数", "目标表", "目标行数"))
            self._log("  " + "-" * 58)
            for cn_name, st in SRC_DST_MAP:
                dt = DST_TABLE_OF[cn_name]
                try:
                    dcur.execute("SET NOCOUNT ON; SELECT COUNT(*) FROM %s" % dt)
                    dc = dcur.fetchone()[0]
                except Exception:
                    dc = -1
                self._log("  %-10s %10d | %-18s %10d" % (cn_name, src_counts[cn_name], dt, dc))
            for t in ("xw_P_PtypePrice", "xw_PtypeUnit"):
                try:
                    dcur.execute("SET NOCOUNT ON; SELECT COUNT(*) FROM %s" % t)
                    self._log("  %-10s %10s | %-18s %10d" % ("(扩展)", 0, t, dcur.fetchone()[0]))
                except Exception:
                    pass
            if self.var_cache.get():
                try:
                    kspc.clear_client_cache()
                    self._log("已清理客户端缓存，请重开管家婆查看。")
                except Exception as e:
                    self._log("清缓存失败：" + str(e)[:100])
            self._log("-" * 62)
            self._log("客户端读取链路验证（xw_GetBasicData）：")
            try:
                for cn_name, n, ok in core.verify_client_readable(dcur):
                    mark = "✔" if ok and n >= 0 else "✘"
                    self._log("  %s %-10s %d 行" % (mark, cn_name, n))
            except Exception as e:
                self._log("  验证失败：" + str(e)[:120])
            self._log("=" * 62)
        except Exception as e:
            self._log("✘ 任务中断：" + str(e))
            self._log(traceback.format_exc(limit=3))
        finally:
            for cn in (src, dst):
                try:
                    cn.close()
                except Exception:
                    pass
            self._set_busy(False)
            self.lbl_state.configure(text="就绪")

    def _do_backup(self):
        def work():
            try:
                cn = self._open("maint")
                cur = cn.cursor()
                pre = core.backup_tables(cur)
                self._log("✔ 备份完成：" + pre)
                cn.close()
                self._load_prefixes()
            except Exception as e:
                self._log("✘ 备份失败：" + str(e)[:160])
        threading.Thread(target=work, daemon=True).start()

    def _do_verify(self):
        def work():
            try:
                cn = self._open("maint")
                cur = cn.cursor()
                pre = core.latest_backup_prefix(cur)
                if not pre:
                    self._log("没有找到 _impbak_ 备份")
                    return
                ok, rows = core.verify_backup(cur, pre)
                self._log("备份完整性：%s  前缀：%s" % (ok, pre))
                for r in rows:
                    t, status, bn, cn, cs_ok = r
                    cs_mark = "[内容同]" if cs_ok else "[内容变]"
                    self._log("  %-22s %-14s 备份=%d 当前=%d %s" % (t, status, bn, cn, cs_mark))
                cn.close()
            except Exception as e:
                self._log("✘ 校验失败：" + str(e)[:160])
        threading.Thread(target=work, daemon=True).start()

    def _do_rollback(self):
        if self._busy:
            messagebox.showwarning("请稍候", "已有任务正在执行。")
            return
        pre = None
        sel = self.lst_pre.curselection()
        if sel:
            pre = self.lst_pre.get(sel[0]).split()[0]
        if not pre or not pre.startswith("_impbak_"):
            pre = None
        if not messagebox.askyesno(
                "确认回滚",
                "将把目标账套 13 张基本资料表恢复为备份内容。\n"
                "备份前缀：%s\n\n回滚会覆盖这些表的当前数据，是否继续？" % (pre or "（最近一次备份）")):
            return
        self._set_busy(True)

        def work():
            try:
                cn = self._open("maint")
                cur = cn.cursor()
                target = pre or core.latest_backup_prefix(cur)
                if not target:
                    raise RuntimeError("没有可用的备份前缀")
                ok, _ = core.verify_backup(cur, target)
                if not ok:
                    raise RuntimeError("备份不完整，已中止（未改动任何数据）")
                core.rollback_tables(cur, target)
                self._log("✔ 已回滚到 " + target)
                cn.close()
            except Exception as e:
                self._log("✘ 回滚失败：" + str(e)[:160])
            finally:
                self._set_busy(False)
        threading.Thread(target=work, daemon=True).start()

    def _do_clearcache(self):
        try:
            n = kspc.clear_client_cache()
            self._log("✔ 已清理客户端缓存文件 %d 个，请重开管家婆。" % (n or 0))
        except Exception as e:
            self._log("✘ 清缓存失败：" + str(e)[:120])

    def _check_update(self):
        def work():
            try:
                import urllib.request, json
                url = "https://api.github.com/repos/DDDNN1234567/kspc-grasp-transfer/releases/latest"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "kspc-gui/" + APP_VER,
                    "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode("utf-8"))
                tag = data.get("tag_name", "?")
                pub = data.get("published_at", "")[:10]
                body = (data.get("body") or "").strip().splitlines()
                first = body[0] if body else ""
                latest = tag.lstrip("vV")
                if latest > APP_VER:
                    self._log("★ 发现新版本：当前 v%s，GitHub 最新 %s（%s）" % (APP_VER, tag, pub))
                    self._log("  更新摘要：%s" % first[:120])
                    self._log("  请到 GitHub Release 页下载新版 exe。")
                else:
                    self._log("✔ 当前 v%s 已是最新（GitHub 最新 %s）" % (APP_VER, tag))
            except Exception as e:
                self._log("✘ 检查更新失败：" + str(e)[:160])
        threading.Thread(target=work, daemon=True).start()

    def _load_prefixes(self):
        def work():
            try:
                cn = self._open("maint")
                cur = cn.cursor()
                pres = core.list_backup_prefixes(cur)
                self.lst_pre.delete(0, "end")
                for p in pres:
                    self.lst_pre.insert("end", p)
                if not pres:
                    self.lst_pre.insert("end", "（暂无备份）")
                cn.close()
            except Exception as e:
                self._log("✘ 读取备份列表失败：" + str(e)[:120])
        threading.Thread(target=work, daemon=True).start()


HELP_TEXT = """竞驰管家婆一键资料互传 v1.2

【它做什么】
把竞驰管理通账套里的基本资料，按管家婆辉煌 TOP15 的规则写入管家婆账套：
往来单位、仓库、职员、商品（含分类与多单位）、库存结存、客户价格跟踪、条码、
以及管家婆官方过程覆盖不到的预设售价4/5、会员价、特价、第3/4 辅助单位。

【使用步骤】
1. 源库：填竞驰所在实例（如 DESKTOP-8P5G8VQ\SQLEXPRESS）、sa 密码，点“刷新库”下拉选择竞驰账套库。
2. 目标库：填管家婆所在实例与账套库，点“测试连接”。
3. 勾选要导的模块（默认全选）；首次建议保持“导入前自动备份目标 13 表”。
4. 点“开始一键导入”，看日志。导入结束会自动输出源-目标行数对照表。
5. 导入完成后重开管家婆，进“基本信息”查看。

【维护页】
备份 13 表 / 校验最近备份（含内容 CHECKSUM 对比）/ 回滚 / 清缓存 / 检查更新。

【限制】
· 竞驰的仓库层级会被拍平。
· 竞驰的品牌、部门、季节、辅助属性暂不导入。
· 期初应收应付按竞驰的 *00 字段导入；运行余额不导。
"""


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
