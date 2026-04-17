## 图片渲染逻辑修改

之前是通过sse的render事件来实现image在前台的呈现的，现在希望删除对render的image渲染逻辑，而是引入了一个新的event：wifi_result

要做的事情就是解析这个wifi_result中的图片images的路径和title，将其渲染到右侧界面上，
记得修改图片布局，现在希望是一个图占一行。

event: wifi_result
data: {
  "renderType": "wifi_simulation",
  "renderData": {
    "preset": "大平层",
    "gridSize": 40,
    "apCount": 1,
    "targetApCount": 3,
    "summary": "大平层 1AP→3AP 补点优化完成；...",
    "stats": {
      "rssi_before": { "mean_rssi": -72.1, "worst_rssi": -90.0, "shape": [42, 42] },
      "rssi_after":  { "mean_rssi": -55.3, "worst_rssi": -78.5, "shape": [42, 42] },
      "stall_before": { "mean_stall_rate": 0.182, "max_stall_rate": 0.564, "shape": [42, 42] },
      "stall_after":  { "mean_stall_rate": 0.021, "max_stall_rate": 0.097, "shape": [42, 42] }
    },
    "images": [
      { "imageId": "..._img_0", "imageUrl": "/api/images/..._img_0", "title": "RSSI 对比图(补点前/后)", "kind": "rssi" },
      { "imageId": "..._img_1", "imageUrl": "/api/images/..._img_1", "title": "卡顿率对比图(补点前/后)", "kind": "stall" }
    ],
    "dataFiles": [
      { "fileId": "..._data_0", "title": "补点前 RSSI 矩阵", "kind": "rssi", "phase": "before", "stats": {...}, "content": {...} },
      { "fileId": "..._data_1", "title": "补点后 RSSI 矩阵", "kind": "rssi", "phase": "after",  "stats": {...}, "content": {...} },
      { "fileId": "..._data_2", "title": "补点前 卡顿率矩阵", "kind": "stall", "phase": "before", "stats": {...}, "content": {...} },
      { "fileId": "..._data_3", "title": "补点后 卡顿率矩阵", "kind": "stall", "phase": "after",  "stats": {...}, "content": {...} }
    ]
  }
}