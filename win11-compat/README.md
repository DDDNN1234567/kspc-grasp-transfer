# Win11 兼容加密锁 DLL

## 文件位置

改造后的 DLL 文件（69,632 字节，已嵌入 Win11 兼容性 manifest）存放在：

```
D:\kspcV81\BZ\server\xMagicSvc.dat
```

备份文件：
- `xMagicSvc.dat.bak` — 原始未改版本

## 改造内容

给 2008 年编译的 32 位 DLL 嵌入了 `RT_MANIFEST` 资源，声明支持 Vista / Win7 / Win8 / Win8.1 / Win10-11，解决 Win11 上 `GetVersionEx` 被 shim 降级导致 DLL 拒绝工作的问题。

## 使用方法

1. 备份原 `xMagicSvc.dat`
2. 用本目录的改造后文件替换（改名 `xMagicSvc.dat`）
3. 启动竞驰软件验证加密狗识别

## 详细日志

见 [改造日志.md](改造日志.md)
