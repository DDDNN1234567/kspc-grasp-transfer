# 加密锁（ET99）Win11 兼容性改造完整说明

## 问题

`D:\kspcV81\BZ\server\xMagicSvc.dat` 是竞驰管理通服务端的 USB 加密锁通信 DLL，在 Windows 11 上识别不到加密锁（序列号 A000194D）。

## 加密锁硬件信息

| 项 | 值 |
|---|---|
| 型号 | 坚石诚信 ET99 |
| 序列号 | A000194D |
| 生产日期 | 2005-11-22（加密锁本体日期） |
| 接口 | USB HID 无驱 |
| 厂家官网 | https://www.jansh.com.cn/product/rockey/et-99/ |

## 排查过程

### 1. 对比两个版本 DLL

| 版本 | 文件位置 | 大小 | 编译日期 | MD5 |
|---|---|---|---|---|
| 2008 版（老） | kspcV81 原始 | 69,696 字节 | 2008-09-10 | 25BCDD8D... |
| 2012 版（新） | kechee\老版本注册写狗 | 55,264 字节 | 2012-12-19 | 443C38CA... |

两版导出函数完全一致（19 个 et_* 接口），依赖 DLL 一致（KERNEL32/SETUPAPI/HID.DLL）。

### 2. 第一次尝试：嵌入兼容性 manifest

2008 版 DLL 调用了 `GetVersionExA` / `GetVersion` 做 OS 版本检测，但没带 manifest。Win11 shim 会降级返回虚假版本号。

- 用 BeginUpdateResource/UpdateResource 嵌入 RT_MANIFEST（ID=1）
- 声明支持 Vista / Win7 / Win8 / Win8.1 / Win10-11
- 结果：嵌入后仍然识别不到加密锁

**结论**：manifest 不是根因。

### 3. 第二次尝试：对比测试

- kechee 目录（2012 版 DLL）能正常识别加密锁
- kspcV81 目录（2008 版 DLL）识别不到

**结论**：根本问题是 2008 版 DLL 太老，和当前加密锁硬件不兼容。

## 两版深度对比

### 为什么 2008 版更大？

| | 2008 版（69,696 字节） | 2012 版（55,264 字节） |
|---|---|---|
| 大小 | 69,696 | 55,264（小 21%） |
| `__GLOBAL_HEAP_SELECTED` | ✅ 有 | ❌ 没有 |
| `__MSVCRT_HEAP_SELECT` | ✅ 有 | ❌ 没有 |
| MSVCRT 运行时字符串 | 多 | 少 |

**原因**：2008 版**静态链接了更多 MSVCRT 运行时库**（heap、stdio、线程局部存储等），所以更大。2012 版更精简，动态依赖系统已有的 MSVCRT.DLL。

### 有没有竞驰自定义修改？

**没有。** 搜索结果：

| 关键词 | 2008 版 | 2012 版 |
|---|---|---|
| `kspc` / `kspcV81` | 0 | 0 |
| `grasp` / `gpj` / `jichi` | 0 | 0 |
| `xw_` / `xMagic` | 0 | 0 |
| `A000194D`（加密锁号） | 0 | 0 |
| `FFFFFFFF`（默认 PID） | 0 | 0 |

**说明**：
- DLL 是标准的 ET99 API 库，没有竞驰软件的自定义修改
- PID（产品 ID）是**运行时传入**的，不是硬编码在 DLL 里
- 竞驰软件在调用 `et_FindToken(pid)` 时传入自己的 PID，DLL 只是通用通信层

### 签名对比

| 文件 | 签名状态 | 签名者 |
|---|---|---|
| 2012 版（当前在用） | ✅ Valid | Feitian Technologies（飞天诚信） |
| 2008 版（原始） | ❌ NotSigned | （无） |

### 为什么不需要补符号、不需要去签名？

1. **`__GLOBAL_HEAP_SELECTED` / `__MSVCRT_HEAP_SELECT` 是 MSVCRT 内部符号**，是链接器自动生成的，不是业务代码。两版功能完全一致，只是运行时链接方式不同。

2. **去掉签名会降低兼容性**：
   - 有签名 → Win11 SmartScreen 不拦，系统信任度更高
   - 无签名 → 可能弹"未知发布者"警告

## 最终解决方案

把 kechee 目录的 2012 版 `xMagicSvc.dat`（55,264 字节）复制到 kspcV81 目录替换。

```
D:\kspcV81\BZ\server\xMagicSvc.dat
├─ 大小: 55,264 字节
├─ 版本: 2012-12-19 编译
├─ 签名: ✅ 飞天诚信 Valid
└─ MD5: 443C38CA4C18D0B9754751A362F71B61
```

测试通过，加密锁 A000194D 正常识别。

## 验证：官网最新版 = 当前在用版

从坚石诚信官网下载最新 SDK（2024/08 上传）对比：

| 文件 | 大小 | MD5 |
|---|---|---|
| 官网最新 FT_ET99_API.dll | 55,264 | 443C38CA... |
| 当前在用 xMagicSvc.dat | 55,264 | 443C38CA... |

**MD5 完全一致，说明我们已经在用最新版了。**

## 备份文件清单

| 文件 | 说明 |
|---|---|
| `xMagicSvc.dat.bak` | 原始 2008 版（未改，无签名） |
| `xMagicSvc.dat.bak_2008_manifest` | 带 Win11 manifest 的 2008 版（无签名） |
| `xMagicSvc.dat` | 当前在用 = 2012 版（=官网最新版，有签名） |

## 厂家资源下载

- 产品页：https://www.jansh.com.cn/product/rockey/et-99/
- API DLL 库（32位）：https://www.jansh.com.cn/wp-content/uploads/2024/08/et99_api_dll.zip
- x64 位库：https://www.jansh.com.cn/wp-content/uploads/2024/08/et99_api_x64_dll.zip
- 软件保护资源包：https://www.jansh.com.cn/wp-content/uploads/2024/08/et99_softfull.zip
- API 手册：https://www.jansh.com.cn/wp-content/uploads/2024/08/et99_doc_api.zip

## 导出函数列表（19 个）

```
MD5_HMAC
et_ChangeUserPIN
et_CloseToken
et_FindToken
et_GenPID
et_GenRandom
et_GenSOPIN
et_GetSN
et_HMAC_MD5
et_OpenToken
et_Read
et_ResetPIN
et_ResetSecurityState
et_SetKey
et_SetupToken
et_TurnOffLED
et_TurnOnLED
et_Verify
et_Write
```

## 常见问题

1. **PID 必须修改后才能使用**：出厂默认 8 个 F（FFFFFFFF），不修改很多功能不能用
2. **64 位系统调用**：32 位程序调 32 位 DLL（放在 SysWOW64），64 位程序调 64 位 DLL（放在 System32）
3. **UserPIN 重试 3 次锁死**：锁死后需 SOPIN 解锁
4. **存储区每次读写最多 60 字节**：超过需分块

改造日期：2026-11-05
