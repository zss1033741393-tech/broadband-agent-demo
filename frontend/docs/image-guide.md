# 贴图指南

## 图片存放位置

### 推荐路径

| 用途 | 路径 | 说明 |
|---|---|---|
| 静态大图（地图、横幅） | `public/images/` | 直接用绝对路径引用，不经 vite 处理 |
| 代码内引用的小图（LOGO、图标） | `src/assets/images/` | vite 会处理，支持 `import` 语法 |

**首次使用需创建目录：**

```bash
mkdir -p frontend/public/images
mkdir -p frontend/src/assets/images
```

---

## 各贴图位置说明

### 1. TopBar — LOGO（左上角）

**文件：** `src/components/Layout/TopBar/index.tsx`  
**当前：** 文字占位"光智"  
**替换方法：**

```tsx
// 推荐：将 logo 文件放在 src/assets/images/logo.png
import logoImg from '@/assets/images/logo.png';

// 替换 <div className={styles.logoPlaceholder}> 这整块为：
<img src={logoImg} alt="光接入智能体" className={styles.logoImg} />
```

**CSS（TopBar.module.css）补充：**

```css
.logoImg {
  height: 32px;
  width: auto;
  object-fit: contain;
}
```

**推荐命名：** `logo.png`（或 `logo.svg`，SVG 更清晰但 PNG 完全可用）  
**推荐尺寸：** 高度 64px 以上（@2x），背景透明，显示时 CSS 限制为 32px 高

---

### 2. Dashboard 左侧 — 贴图预留区域（Banner）

**文件：** `src/pages/Dashboard/LeftPanel/index.tsx`  
**当前：** 虚线框"贴图预留区域"  
**替换方法：**

```tsx
// 将图片放在 public/images/dashboard-banner.png
// 直接用绝对路径（public 目录下文件）：
<div className={styles.bannerArea}>
  <img
    src="/images/dashboard-banner.png"
    alt="区域概况"
    className={styles.bannerImg}
  />
</div>
```

**CSS（LeftPanel.module.css）补充：**

```css
.bannerImg {
  width: 100%;
  height: 200px;
  object-fit: cover;
  border-radius: 8px;
  display: block;
}
```

**推荐命名：** `dashboard-banner.png`  
**推荐尺寸：** 420 × 200px（与占位区完全匹配）

---

### 3. Dashboard 右侧 — 顶部横幅（TopBanner）

**文件：** `src/pages/Dashboard/RightArea/index.tsx`  
**当前：** 虚线框"顶部横幅预留区域（1361 × 130）"  
**替换方法：**

```tsx
// 将图片放在 public/images/top-banner.png
<div className={styles.topBanner}>
  <img
    src="/images/top-banner.png"
    alt="顶部横幅"
    className={styles.topBannerImg}
  />
</div>
```

**CSS（RightArea.module.css）补充：**

```css
.topBannerImg {
  width: 100%;
  height: 130px;
  object-fit: cover;
  display: block;
}
```

**推荐命名：** `top-banner.png`  
**推荐尺寸：** 1361 × 130px

---

### 4. Dashboard 右侧 — 地图底图（MapView）

**文件：** `src/pages/Dashboard/RightArea/index.tsx`  
**当前：** 灰色网格"地图底图预留区域"，告警标签浮层叠在其上  
**替换方法：**

```tsx
// 将地图截图放在 public/images/map-bg.png
// 注意：mapArea 是 position: relative，AlertOverlay 绝对定位浮在地图上
// 只替换占位 div，保留 <AlertOverlay />

<div className={styles.mapArea}>
  <img
    src="/images/map-bg.png"
    alt="区域地图"
    className={styles.mapBgImg}
  />
  <AlertOverlay />
</div>
```

**CSS（RightArea.module.css）补充：**

```css
.mapBgImg {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
```

**推荐命名：** `map-bg.png`  
**推荐尺寸：** 与 mapArea 容器匹配（约 1361 × 824px）  
**注意：** AlertOverlay 的告警标签用 `top/left` 百分比定位，换图后需按实际地图坐标调整 `AlertOverlay/index.tsx` 里各标签的百分比值

---

### 5. Workspace 右侧 — 空状态图（EmptyState）

**文件：** `src/pages/Workspace/RightPanel/EmptyState/index.tsx`  
**当前：** SVG 网络拓扑示意图  
**替换方法：**

```tsx
// 将图片放在 src/assets/images/empty-topology.png
import emptyImg from '@/assets/images/empty-topology.png';

// 替换 <svg> 整块为：
<img src={emptyImg} alt="网络拓扑" className={styles.topoImg} />
```

**CSS（EmptyState.module.css）补充：**

```css
.topoImg {
  width: 200px;
  height: auto;
  opacity: 0.6;
}
```

**推荐命名：** `empty-topology.png` 或 `empty-topology.svg`  
**推荐尺寸：** 200 × 200px 左右，背景透明

---

## 命名规范

| 规则 | 示例 |
|---|---|
| 全小写，单词用连字符 `-` 分隔 | `dashboard-banner.png` ✅ |
| 按用途前缀区分 | `map-bg.png` / `top-banner.png` / `logo.svg` |
| 不用中文、空格、特殊符号 | `区域地图.png` ❌ |
| 标注尺寸或用途后缀（可选） | `map-bg-1361x824.png` |

---

## 格式选择建议

| 场景 | 推荐格式 |
|---|---|
| LOGO、图标、线条图 | SVG（无损缩放） |
| 截图、地图、横幅大图 | PNG（需要透明）/ JPEG（纯背景） |
| 动态图（可选） | GIF / WebP |

---

## 快速验证

替换图片后，在浏览器 DevTools → Network 里过滤 `Img`，确认图片返回 200，没有 404。
