# -*- coding: utf-8 -*-
"""
竞驰管理通（KSPC） -> 管家婆辉煌 TOP15 适配器
=================================================
把竞驰管理通（v81，ProductCode=kspc，dataVersion=mS.D.08.8.1.1.000）的
基本信息表，按基本资料对应关系导入管家婆辉煌 TOP15 账套（HH15new）。

通道：一律走管家婆官方存储过程（p_hh_BasicInsertB/K/P/E_Commodity、
      p_hh_ModInitGoodsStocks_SNMng_Package、p_hh_ImportPtypePriceGZ），
      编号/拼音/层级/子级计数/updatetag 全部由官方维护。

竞驰源表：
      T_base_wldw_inner      往来单位（id/par_id 树）
      t_base_storage_inner   仓库
      t_base_employees       职员
      t_base_goods_inner     商品（117 列，unit1~unit4 + unitrelation*）
      t_base_goodsstock      库存（当前结存）
      t_base_price           单位价格跟踪
      t_base_GoodsBar        条码

与千业 Bas 的关键差异：
      * 竞驰无 00000 根节点：par_id=0 即一级，导入时挂管家婆 00000 根下
      * 商品支持 4 个单位（unit1 基本 + unit2/3/4 辅助），官方过程只收 2 个，
        第 3/4 单位直写 xw_PtypeUnit
      * 竞驰有 5 个预设售价 + 批发价 + 会员价 + 特价，官方过程只收 3 个预设，
        其余直写 xw_P_PtypePrice
"""

import sys
import os
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyodbc
import gpj_top15_core as core

# ---------------- 源库默认 ----------------
SRC_SERVER = r"DESKTOP-8P5G8VQ\SQLEXPRESS"
DST_SERVER = r"DESKTOP-8P5G8VQ\SQLSERVER"
DST_DB = "HH15new"
SRC_DB = "kspcDefault"

# 竞驰源表
T_WLDW = "T_base_wldw_inner"
T_STORAGE = "t_base_storage_inner"
T_EMP = "t_base_employees"
T_GOODS = "t_base_goods_inner"
T_STOCK = "t_base_goodsstock"
T_PRICE = "t_base_price"
T_BAR = "t_base_GoodsBar"

# 竞驰核心四表（用于识别账套类型）
KSPC_CORE = [T_WLDW, T_STORAGE, T_EMP, T_GOODS]

# 模块
MODULES = ["unit", "warehouse", "employee", "goods", "stockini",
           "price", "barcode", "extprice", "extunit"]
MODULE_CN = {
    "unit": "往来单位",
    "warehouse": "仓库",
    "employee": "职员",
    "goods": "商品",
    "stockini": "库存结存",
    "price": "价格跟踪",
    "barcode": "条码",
    "extprice": "扩展价格(预设4/5/会员价/特价)",
    "extunit": "扩展辅助单位(第3/4单位)",
}

# 竞驰价格列 -> 管家婆自定义价格类型（官方过程覆盖不到的）
EXT_PRICE_MAP = [
    ("price4", "0119", "预设售价4"),
    ("price5", "0120", "预设售价5"),
    ("vipprice", "0121", "会员价"),
    ("specialprice", "0122", "特价"),
]


# ---------------- 基础工具 ----------------
def _rows(cur, sql, args=()):
    """查询并返回 dict 列表（键统一小写）"""
    cur.execute(sql, args)
    cols = [d[0] for d in cur.description]
    out = []
    for r in cur.fetchall():
        out.append({c.lower(): v for c, v in zip(cols, r)})
    return out


def _s(v, default=""):
    """安全转字符串"""
    if v is None:
        return default
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def _n(v, default=0):
    """安全转 float"""
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _flag(v):
    """竞驰 int 标志 -> 0/1"""
    try:
        return 1 if int(v) == 1 else 0
    except Exception:
        return 0


# ---------------- 账套识别 ----------------
def is_kspc_database(cur):
    """校验是否为竞驰管理通账套（核心四表存在）"""
    cur.execute("""
SELECT COUNT(*) FROM sys.tables
WHERE name IN ('T_base_wldw_inner','t_base_storage_inner','t_base_employees','t_base_goods_inner')""")
    return cur.fetchone()[0] == 4


def kspc_version(cur):
    """读取竞驰账套版本信息"""
    try:
        rs = _rows(cur, "SELECT name, sysvalue FROM T_Sys_Data WHERE name IN ('dataVersion','ProductCode','isopen','period')")
        d = {r["name"]: _s(r["sysvalue"]) for r in rs}
        return d.get("dataVersion", ""), d.get("ProductCode", ""), d.get("isopen", "0"), d.get("period", "1")
    except Exception:
        return "", "", "0", "1"


# ---------------- 级联数字化 ----------------
def digi_map(rows, id_key="id", parent_key="par_id", order_key="orderly"):
    """
    把竞驰的 id/par_id 树，BFS 级联生成管家婆树编号：
      一级 00001/00002...
      二级 0000100001...
    返回 (id2code dict, [(row, code), ...] 按 BFS 顺序)
    防环：visited 集合
    """
    if not rows:
        return {}, []
    idx = {}
    for r in rows:
        idx[r[id_key]] = r
    # 找顶层：par_id 为 0/None 或 父 id 不存在
    roots = []
    for r in rows:
        p = r.get(parent_key)
        if p is None or int(p) == 0 or int(p) not in idx:
            roots.append(r)
    roots.sort(key=lambda x: (_n(x.get(order_key)), x[id_key]))

    kids = {}
    for r in rows:
        p = r.get(parent_key)
        if p is None:
            continue
        p = int(p)
        if p == 0 or p not in idx:
            continue
        kids.setdefault(p, []).append(r)

    result = {}
    order = []
    q = deque()
    for i, r in enumerate(roots, 1):
        q.append((r, "%05d" % i, 1))
    visited = set()
    while q:
        r, code, depth = q.popleft()
        rid = r[id_key]
        if rid in visited:
            continue
        visited.add(rid)
        result[rid] = code
        order.append((r, code))
        cs = kids.get(rid, [])
        cs.sort(key=lambda x: (_n(x.get(order_key)), x[id_key]))
        for j, c in enumerate(cs, 1):
            q.append((c, code + "%05d" % j, depth + 1))
    return result, order


def root_children_count(rows, id_key="id", parent_key="par_id"):
    """每个父 id 的直接子级数（用于 soncount 校验）"""
    idx = set(r[id_key] for r in rows)
    cnt = {}
    for r in rows:
        p = r.get(parent_key)
        if p is None:
            continue
        p = int(p)
        if p == 0 or p not in idx:
            continue
        cnt[p] = cnt.get(p, 0) + 1
    return cnt


# ---------------- 读取源数据 ----------------
def load_units(cur):
    return _rows(cur, """
SELECT id, par_id, code, fullname, name, pym, addr, tel, postcode, person, tax,
       bankcount, ystotal00, yftotal00, yushoutotal00, yufutotal00,
       ys_xyd, yf_xyd, comment, isstop, del, discount, Fax, EMAIL, orderly
FROM %s
ORDER BY par_id, orderly, id""" % T_WLDW)


def load_storages(cur):
    return _rows(cur, """
SELECT id, par_id, code, fullname, name, pym, comment, isstop, del, leveal, orderly
FROM %s
ORDER BY par_id, orderly, id""" % T_STORAGE)


def load_employees(cur):
    return _rows(cur, """
SELECT id, par_id, code, fullname, name, pym, tel, addr, comment,
       birthday, mobileNo, LowDiscount, del, depid
FROM %s
ORDER BY par_id, id""" % T_EMP)


def load_goods(cur):
    """商品：取常用列，缺列时容错"""
    cols = ["ID", "PAR_ID", "code", "barcode", "fullname", "name", "standard", "xh", "addr",
            "unit1", "unit2", "unit3", "unit4",
            "unitrelation", "unitrelation2", "unitrelation3", "unitrelation4",
            "price", "price1", "price2", "price3", "price4", "price5", "pf_price",
            "recprice", "recprice1", "lowprice", "vipprice", "specialprice",
            "costmode", "pym", "warnup", "warndown", "defaultrate", "discount",
            "comment", "isstop", "del", "orderly", "sonnum"]
    cur.execute("SELECT c.name FROM sys.columns c WHERE c.object_id=OBJECT_ID(?)", T_GOODS)
    have = set(r[0].lower() for r in cur.fetchall())
    sel = [c for c in cols if c.lower() in have]
    sql = "SELECT %s FROM %s ORDER BY PAR_ID, orderly, ID" % (", ".join(sel), T_GOODS)
    return _rows(cur, sql)


def load_stocks(cur):
    try:
        return _rows(cur, """
SELECT id, goodsid, stid, JobNumber, outdate, goodsqty, price, total
FROM %s""" % T_STOCK)
    except Exception:
        return []


def load_prices(cur):
    try:
        return _rows(cur, """
SELECT id, goodsid, wldwid, costprice, saleprice, buydiscount, salediscount, unitType
FROM %s""" % T_PRICE)
    except Exception:
        return []


def load_barcodes(cur):
    try:
        return _rows(cur, "SELECT goodsID, barCode, Unit FROM %s" % T_BAR)
    except Exception:
        return []


# ---------------- 目标侧工具 ----------------
def existing_usercodes(cur, table, code_col):
    cur.execute("SELECT %s FROM %s WHERE %s IS NOT NULL" % (code_col, table, code_col))
    return set(_s(r[0]) for r in cur.fetchall())


def ensure_ext_pricetypes(cur):
    """补齐扩展价格类型 0119-0122（自定义，IsSystem=0）"""
    made = []
    for _, pid, name in EXT_PRICE_MAP:
        cur.execute("SELECT COUNT(*) FROM xw_P_PriceType WHERE PRTypeId=?", pid)
        if cur.fetchone()[0] == 0:
            cur.execute("""
INSERT INTO xw_P_PriceType (PRTypeId, PRName, PRDisName, PRType, IsVisible, IsSystem,
                            IsEdit, IsSet, Comment, URec, ParRec, USonnum, updatetag, IsBaseVis)
VALUES (?, ?, ?, 0, 1, 0, 1, 1, '', 0, 0, 0, 10000, 1)""", pid, name, name)
            made.append(pid)
    return made


def update_updatetag(cur):
    for t in ["btype", "ptype", "Stock", "employee"]:
        try:
            cur.execute("UPDATE %s SET updatetag=10000 WHERE updatetag<>10000" % t)
        except Exception:
            pass
    try:
        cur.execute("UPDATE xw_BaseUpdateTag SET UpdateTag=0")
    except Exception:
        pass


def clear_client_cache(logcb=None):
    """清理管家婆客户端 localData 缓存"""
    import glob
    pats = [r"F:\GRASPⅡTOP15\Data\localData\*-00000-*"]
    n = 0
    for p in pats:
        for f in glob.glob(p):
            try:
                os.remove(f)
                n += 1
            except Exception:
                pass
    if logcb:
        logcb("已清理客户端缓存 %d 个文件" % n)
    return n


# ---------------- 导入编排 ----------------
def _import_body(src_cur, dst_cur, modules=None, logcb=None, incremental=False):
    """
    竞驰 -> 管家婆 主流程
    src_cur : 竞驰库游标
    dst_cur : 管家婆账套游标
    modules : 要导入的模块列表，None=全部
    incremental : True 时已存在的 usercode 跳过（基础资料不重复建）
    """
    log = logcb or (lambda s: None)
    mods = modules or MODULES
    stat = {m: 0 for m in MODS_KEYS}
    stat["fail"] = 0
    errs = []

    # 1) 读取源
    log("读取竞驰源数据…")
    units = load_units(src_cur)
    storages = load_storages(src_cur)
    emps = load_employees(src_cur)
    goods = load_goods(src_cur)
    log("  单位 %d / 仓库 %d / 职员 %d / 商品 %d" % (len(units), len(storages), len(emps), len(goods)))

    # 2) 级联编号
    umap, uorder = digi_map(units)
    kmap, korder = digi_map(storages)
    emap, eorder = digi_map(emps, order_key="id")
    gmap, gorder = digi_map(goods, id_key="id", parent_key="par_id")

    # 3) 已存在编号（增量用）
    ex_u = existing_usercodes(dst_cur, "btype", "busercode")
    ex_k = existing_usercodes(dst_cur, "Stock", "kusercode")
    ex_e = existing_usercodes(dst_cur, "employee", "eusercode")
    ex_p = existing_usercodes(dst_cur, "ptype", "pusercode")

    # 记录"竞驰 id -> 官方过程实际生成的树编号"，子级父引用必须用它
    # （官方过程按库内现状生成编号，不一定等于我们预期的 00001 行序）
    u_tree, k_tree, e_tree, g_tree = {}, {}, {}, {}

    # 4) 单位
    if "unit" in mods:
        log("导入往来单位…")
        for row, code in uorder:
            ucode = _s(row.get("code")) or code
            rid = row.get("id")
            if incremental and ucode in ex_u:
                stat["unit_skip"] = stat.get("unit_skip", 0) + 1
                u_tree[rid] = _find_tree(dst_cur, "btype", "busercode", ucode)
                continue
            parid = "00000"
            pid = row.get("par_id")
            if pid and int(pid) in u_tree:
                parid = u_tree[int(pid)]
            try:
                # 注意：管家婆官方过程里 @FullName=编号、@UserCode=全名（语义反直觉）
                rc, rt, err = core.call_unit(
                    dst_cur, parid, ucode, _s(row.get("fullname")),
                    name=_s(row.get("name")), namepy=_s(row.get("pym")),
                    address=_s(row.get("addr")), tel=_s(row.get("tel")),
                    postcode=_s(row.get("postcode")), person=_s(row.get("person")),
                    taxno=_s(row.get("tax")), bankacct=_s(row.get("bankcount")),
                    art00=_s(row.get("ystotal00")), apt00=_s(row.get("yftotal00")),
                    yrt00=_s(row.get("yushoutotal00")), ypt00=_s(row.get("yufutotal00")),
                    arup=_s(row.get("ys_xyd")), apup=_s(row.get("yf_xyd")),
                    comment=_s(row.get("comment")), fax=_s(row.get("Fax")),
                    email=_s(row.get("EMAIL"))
                )
                if rc is not None and rc < 0:
                    stat["fail"] += 1
                    errs.append("单位 %s: rc=%s %s" % (ucode, rc, err))
                else:
                    stat["unit"] += 1
                    ex_u.add(ucode)
                    u_tree[rid] = rt
            except Exception as e:
                stat["fail"] += 1
                errs.append("单位 %s: %s" % (ucode, str(e)[:120]))

    # 5) 仓库
    if "warehouse" in mods:
        log("导入仓库…")
        for row, code in korder:
            kcode = _s(row.get("code")) or code
            rid = row.get("id")
            if incremental and kcode in ex_k:
                stat["warehouse_skip"] = stat.get("warehouse_skip", 0) + 1
                k_tree[rid] = _find_tree(dst_cur, "Stock", "kusercode", kcode)
                continue
            parid = "00000"
            # 管家婆仓库不分层：带子级的仓库会被判为"类仓库"，不能挂库存（rc=-7）
            # 故竞驰仓库一律平铺到根下，名称保留原值
            try:
                # @fullname=编号、@usercode=全名
                rc, rt, err = core.call_warehouse(
                    dst_cur, parid, kcode, _s(row.get("fullname")),
                    name=_s(row.get("name")), namepy=_s(row.get("pym")),
                    comment=_s(row.get("comment"))
                )
                if rc is not None and rc < 0:
                    stat["fail"] += 1
                    errs.append("仓库 %s: rc=%s %s" % (kcode, rc, err))
                else:
                    stat["warehouse"] += 1
                    ex_k.add(kcode)
                    k_tree[rid] = rt
            except Exception as e:
                stat["fail"] += 1
                errs.append("仓库 %s: %s" % (kcode, str(e)[:120]))

    # 6) 职员
    if "employee" in mods:
        log("导入职员…")
        for row, code in eorder:
            ecode = _s(row.get("code")) or code
            rid = row.get("id")
            if incremental and ecode in ex_e:
                stat["employee_skip"] = stat.get("employee_skip", 0) + 1
                e_tree[rid] = _find_tree(dst_cur, "employee", "eusercode", ecode)
                continue
            parid = "00000"
            pid = row.get("par_id")
            if pid and int(pid) in e_tree:
                parid = e_tree[int(pid)]
            try:
                # @fullname=编号、@usercode=全名
                rc, rt, err = core.call_employee(
                    dst_cur, parid, ecode, _s(row.get("fullname")),
                    namepy=_s(row.get("pym")), birthday=_s(row.get("birthday")),
                    tel=_s(row.get("tel")), address=_s(row.get("addr")),
                    lowdisc=_s(row.get("lowdiscount")), ecomment=_s(row.get("comment"))
                )
                if rc is not None and rc < 0:
                    stat["fail"] += 1
                    errs.append("职员 %s: rc=%s %s" % (ecode, rc, err))
                else:
                    stat["employee"] += 1
                    ex_e.add(ecode)
                    e_tree[rid] = rt
            except Exception as e:
                stat["fail"] += 1
                errs.append("职员 %s: %s" % (ecode, str(e)[:120]))

    # 7) 商品
    if "goods" in mods:
        log("导入商品…")
        for row, code in gorder:
            pcode = _s(row.get("code")) or code
            rid = row.get("id")
            if incremental and pcode in ex_p:
                stat["goods_skip"] = stat.get("goods_skip", 0) + 1
                g_tree[rid] = _find_tree(dst_cur, "ptype", "pusercode", pcode)
                continue
            parid = "00000"
            pid = row.get("par_id")
            if pid and int(pid) in g_tree:
                parid = g_tree[int(pid)]
            u1 = _s(row.get("unit1"))
            # 竞驰商品分类（unit1 为空）在管家婆里单位是"无"
            if not u1:
                u1 = "无"
            u2 = _s(row.get("unit2"))
            rate = _s(row.get("unitrelation"))
            # 官方过程校验：辅助单位名与换算率必须同时有或同时无（否则报 -28）
            if (not u2) or rate in ("0", "0.0", "0.00", "0.0000"):
                u2, rate = "", ""
            elif not rate:
                rate = "1"
            try:
                # @FullName=编号、@UserCode=全名（官方过程语义反直觉，勿调换）
                rc, rt, err = core.call_goods(
                    dst_cur, parid, pcode, _s(row.get("fullname")),
                    name=_s(row.get("name")), namepy=_s(row.get("pym")),
                    standard=_s(row.get("standard")), area=_s(row.get("addr")),
                    costmode=_s(row.get("costmode")), comment=_s(row.get("comment")),
                    unit=u1, ucode=_s(row.get("barcode")),
                    saleprice=_s(row.get("price")),
                    pre1=_s(row.get("price1")), pre2=_s(row.get("price2")),
                    pre3=_s(row.get("price3")),
                    sendprice=_s(row.get("pf_price")),
                    lowsaleprice=_s(row.get("lowprice")),
                    unit1=u2, unitrate1=rate,
                    defaulttax=_s(row.get("defaultrate"))
                )
                if rc is not None and rc < 0:
                    stat["fail"] += 1
                    errs.append("商品 %s: rc=%s %s" % (pcode, rc, err))
                else:
                    stat["goods"] += 1
                    ex_p.add(pcode)
                    g_tree[rid] = rt
            except Exception as e:
                stat["fail"] += 1
                errs.append("商品 %s: %s" % (pcode, str(e)[:120]))

    # 8) 商品编号 -> 树编号 反查（明细用）
    pcode2tree = real_map(dst_cur, "ptype", "pusercode", "ptypeid")
    kcode2tree = real_map(dst_cur, "Stock", "kusercode", "ktypeid")
    bcode2tree = real_map(dst_cur, "btype", "busercode", "btypeid")

    # 9) 库存（当前结存）
    if "stockini" in mods:
        log("导入库存结存…")
        stocks = load_stocks(src_cur)
        # 源 goodsid/stid 是竞驰 id，转成自定义编号再转树编号
        gid2code = {r["id"]: (_s(r.get("code")) or gmap.get(r["id"], "")) for r in goods}
        kid2code = {r["id"]: (_s(r.get("code")) or kmap.get(r["id"], "")) for r in storages}
        for s in stocks:
            gid = s.get("goodsid")
            sid = s.get("stid")
            gcode = gid2code.get(gid, "")
            kcode = kid2code.get(sid, "")
            pid = pcode2tree.get(gcode, "")
            kid = kcode2tree.get(kcode, "")
            if not pid or not kid:
                stat["fail"] += 1
                errs.append("库存 goodsid=%s stid=%s 无法解析编号" % (gid, sid))
                continue
            pfull = _full_of(dst_cur, "ptype", "ptypeid", "pfullname", pid)
            kfull = _full_of(dst_cur, "Stock", "ktypeid", "kfullname", kid)
            try:
                rc, oid, err = core.call_stockini(
                    dst_cur, pid, pfull, kid, kfull,
                    _s(s.get("goodsqty")), total=_s(s.get("total")),
                    jobno=_s(s.get("jobnumber")), createdate=_s(s.get("outdate"))
                )
                if rc is not None and rc < 0:
                    stat["fail"] += 1
                    errs.append("库存 %s/%s: rc=%s %s" % (gcode, kcode, rc, err))
                else:
                    stat["stockini"] += 1
            except Exception as e:
                stat["fail"] += 1
                errs.append("库存 %s/%s: %s" % (gcode, kcode, str(e)[:120]))

    # 10) 价格跟踪
    if "price" in mods:
        log("导入价格跟踪…")
        prices = load_prices(src_cur)
        gid2code = {r["id"]: (_s(r.get("code")) or gmap.get(r["id"], "")) for r in goods}
        uid2code = {r["id"]: (_s(r.get("code")) or umap.get(r["id"], "")) for r in units}
        for p in prices:
            gcode = gid2code.get(p.get("goodsid"), "")
            bcode = uid2code.get(p.get("wldwid"), "")
            pid = pcode2tree.get(gcode, "")
            bid = bcode2tree.get(bcode, "")
            if not pid or not bid:
                continue
            pfull = _full_of(dst_cur, "ptype", "ptypeid", "pfullname", pid)
            bfull = _full_of(dst_cur, "btype", "btypeid", "bfullname", bid)
            try:
                rc, oid, err = core.call_pricefollow(
                    dst_cur, bid, bfull, pid, pfull, punit="",
                    buyprice=_s(p.get("costprice")), saleprice=_s(p.get("saleprice")),
                    buydisc=_s(p.get("buydiscount")), saledisc=_s(p.get("salediscount"))
                )
                if rc is not None and rc < 0:
                    stat["fail"] += 1
                    errs.append("价格 %s/%s: rc=%s %s" % (bcode, gcode, rc, err))
                else:
                    stat["price"] += 1
            except Exception as e:
                stat["fail"] += 1
                errs.append("价格 %s/%s: %s" % (bcode, gcode, str(e)[:120]))

    # 11) 条码（直写）
    if "barcode" in mods:
        log("导入条码…")
        bars = load_barcodes(src_cur)
        gid2code = {r["id"]: (_s(r.get("code")) or gmap.get(r["id"], "")) for r in goods}
        buf = []
        for b in bars:
            gcode = gid2code.get(b.get("goodsid"), "")
            pid = pcode2tree.get(gcode, "")
            bc = _s(b.get("barcode"))
            if not pid or not bc:
                continue
            uid = str(int(_n(b.get("unit"), 0)))
            buf.append((pid, uid, bc))
        if buf:
            # 去重
            seen = set()
            uniq = []
            for t in buf:
                if t in seen:
                    continue
                seen.add(t)
                uniq.append(t)
            pids = sorted(set(t[0] for t in uniq))
            try:
                dst_cur.execute("DELETE FROM xw_PtypeBarCode WHERE PTypeId IN (%s)"
                                % ",".join("?" * len(pids)), *pids)
            except Exception:
                pass
            for pid, uid, bc in uniq:
                try:
                    dst_cur.execute("""INSERT INTO xw_PtypeBarCode
(PTypeId, UnitID, BarCode, Ordid, keyid, kwtypeid)
VALUES (?, ?, ?, 0, NEWID(), '')""", pid, uid, bc)
                    stat["barcode"] += 1
                except Exception as e:
                    stat["fail"] += 1
                    errs.append("条码 %s: %s" % (bc, str(e)[:100]))

    # 12) 扩展价格（预设4/5、会员价、特价）直写
    if "extprice" in mods:
        log("导入扩展价格…")
        made = ensure_ext_pricetypes(dst_cur)
        if made:
            log("  已补齐价格类型: %s" % ", ".join(made))
        gid2code = {r["id"]: (_s(r.get("code")) or gmap.get(r["id"], "")) for r in goods}
        for r in goods:
            gcode = gid2code.get(r.get("id"), "")
            pid = pcode2tree.get(gcode, "")
            if not pid:
                continue
            for col, pidtype, _nm in EXT_PRICE_MAP:
                val = _n(r.get(col), 0)
                if val <= 0:
                    continue
                try:
                    dst_cur.execute("DELETE FROM xw_P_PtypePrice WHERE PTypeId=? AND PRTypeId=? AND UnitID='0'",
                                    pid, pidtype)
                    dst_cur.execute("""INSERT INTO xw_P_PtypePrice
(PTypeId, UnitID, PRTypeId, Price, UpDateDt, KeyId)
VALUES (?, '0', ?, ?, GETDATE(), NEWID())""", pid, pidtype, val)
                    stat["extprice"] += 1
                except Exception as e:
                    stat["fail"] += 1
                    errs.append("扩展价 %s/%s: %s" % (gcode, pidtype, str(e)[:100]))

    # 13) 扩展辅助单位（第3/4单位）直写
    if "extunit" in mods:
        log("导入扩展辅助单位…")
        gid2code = {r["id"]: (_s(r.get("code")) or gmap.get(r["id"], "")) for r in goods}
        for r in goods:
            gcode = gid2code.get(r.get("id"), "")
            pid = pcode2tree.get(gcode, "")
            if not pid:
                continue
            for slot, (ucol, rcol) in enumerate([("unit3", "unitrelation2"),
                                                ("unit4", "unitrelation3")], start=2):
                un = _s(r.get(ucol))
                rt = _n(r.get(rcol), 0)
                if not un or rt <= 0:
                    continue
                try:
                    dst_cur.execute("""DELETE FROM xw_PtypeUnit
WHERE PTypeId=? AND Ordid=?""", pid, str(slot))
                    dst_cur.execute("""INSERT INTO xw_PtypeUnit
(PTypeId, Unit1, URate, IsBase, Comment, Ordid, keyid)
VALUES (?, ?, ?, 0, '', ?, NEWID())""", pid, un, rt, str(slot))
                    stat["extunit"] += 1
                except Exception as e:
                    stat["fail"] += 1
                    errs.append("扩展单位 %s/%s: %s" % (gcode, un, str(e)[:100]))

    # 14) 归位
    update_updatetag(dst_cur)
    log("updatetag 已归位 10000")
    return stat, errs


MODS_KEYS = ["unit", "warehouse", "employee", "goods", "stockini", "price", "barcode", "extprice", "extunit"]


def real_map(cur, table, code_col, id_col):
    """自定义编号 -> 树编号"""
    cur.execute("SELECT %s, %s FROM %s" % (code_col, id_col, table))
    return {_s(r[0]): _s(r[1]) for r in cur.fetchall() if r[0]}


def _find_tree(cur, table, code_col, code):
    """按自定义编号反查实际树编号"""
    cur.execute("SELECT %s FROM %s WHERE %s=?" % (
        {"btype": "btypeid", "ptype": "ptypeid", "Stock": "ktypeid",
         "employee": "etypeid"}[table], table, code_col), code)
    r = cur.fetchone()
    return _s(r[0]) if r else ""


def _get_sysdata(cur, name):
    try:
        cur.execute("SELECT SubValue FROM sysdata WHERE SubName=?", name)
        r = cur.fetchone()
        return _s(r[0]) if r else ""
    except Exception:
        return ""


def _set_sysdata(cur, name, val):
    try:
        cur.execute("UPDATE sysdata SET SubValue=? WHERE SubName=?", str(val), name)
    except Exception:
        pass


def import_from_db(src_cur, dst_cur, modules=None, logcb=None, incremental=False):
    """
    竞驰 -> 管家婆 主流程（含期初反开账包装）。
    期初应收/应付与库存期初要求账套处于"未开账"状态，
    导入期间临时置 iniover=0，结束后（含异常）恢复原值。
    """
    log = logcb or (lambda s: None)
    mods = modules or MODULES
    need_ini = ("unit" in mods) or ("stockini" in mods)
    old = _get_sysdata(dst_cur, "iniover") if need_ini else None
    if need_ini and old == "1":
        _set_sysdata(dst_cur, "iniover", "0")
        log("目标账套已开账，临时置 iniover=0 以便导入期初（完成后自动恢复）")
    try:
        return _import_body(src_cur, dst_cur, modules, logcb, incremental)
    finally:
        if need_ini and old == "1":
            _set_sysdata(dst_cur, "iniover", "1")
            log("已恢复开账状态 iniover=1")


def _full_of(cur, table, id_col, full_col, tid):
    cur.execute("SELECT %s FROM %s WHERE %s=?" % (full_col, table, id_col), tid)
    r = cur.fetchone()
    return _s(r[0]) if r else ""


def stats_text(stat):
    parts = []
    for k in MODS_KEYS:
        v = stat.get(k, 0)
        sk = stat.get(k + "_skip", 0)
        if v or sk:
            parts.append("%s %d%s" % (MODULE_CN.get(k, k), v, (" (跳过%d)" % sk) if sk else ""))
    if stat.get("fail"):
        parts.append("失败 %d" % stat["fail"])
    return "；".join(parts) if parts else "无数据"
