# 快速开始

## 安装

```bash
git clone https://github.com/Iamnobody78/cognify-engine.git
cd cognify-engine
pip install -e .          # (P2: PyPI 发布后 pip install cognify-engine)
```

## 状态与认证

```bash
python cli/cognify.py status          # 产品状态
python cli/cognify.py cert            # 认证 (5 项检查)
python cli/cognify.py verify --unified  # 三仓库融合验证
```

## 插件

```bash
python cli/cognify.py plugin list            # 7 插件清单
python cli/cognify.py plugin enable governance  # 热启用
python cli/cognify.py plugin disable simulation # 热禁用 (幂等)
python cli/cognify.py pluginify --all        # P.L.U.G.I.N. 六步法验证
```

## 认知服务 (P0)

```bash
python cli/cognify.py serve --port 8080
curl -X POST http://localhost:8080/mce -H "Content-Type: application/json" \
     -d '{"input": "构建一个自主迭代系统"}'
```

## 元能力

```bash
python cli/cognify.py meta --status   # 25 维元能力
python cli/cognify.py debt scan       # 债务扫描
python cli/cognify.py heartbeat       # MMC 认知心跳
```
