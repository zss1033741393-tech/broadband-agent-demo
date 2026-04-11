"""
分钟表 Schema 管理模块。
天表→分钟表字段映射，schema 只输出映射关系，让 LLM 自己判断下钻方向。
"""

import logging
import re

logger = logging.getLogger(__name__)

# 天表维度 → 分钟表字段映射（带中文描述）
# 格式: "天表字段 (含义)" → ["分钟表字段 (含义)", ...]
DIMENSION_FIELD_MAPPING = {
    "Stability": {
        "count_mean (除去周期DGI用户外的周期内告警平均次数扣分)": [
            "unclearedAlarmCount_A (A侧未清除告警数量)",
            "alarmCount (总告警数量)",
            "alarmType_list (告警类型列表)",
            "unclearedAlarmCount_H (H侧未清除告警数量)",
        ],
        "count_max (除去周期DGI用户外的周期内天的告警最大次数扣分)": [
            "unclearedAlarmCount_A (A侧未清除告警数量)",
            "alarmCount (总告警数量)",
            "alarmType_list (告警类型列表)",
            "unclearedAlarmCount_H (H侧未清除告警数量)",
        ],
        "interruption_same_day_max (当天中断时长最大值扣分)": [
            "unclearedAlarmCount_A (A侧未清除告警数量)",
            "alarmCount (总告警数量)",
            "alarmType_list (告警类型列表)",
            "unclearedAlarmCount_H (H侧未清除告警数量)",
            "zeroNegotiationRxRateCnt (协商接收速率为0的次数)",
            "zeroNegotiationTxRatePercent (协商发送速率为0的占比)",
            "zeroAchievableRateCnt (可达速率等于0的次数)",
            "zeroAchievableRatePercent (可达速率等于0的占比)",
        ],
        "interruption_same_day (当天中断时长和扣分)": [
            "unclearedAlarmCount_A (A侧未清除告警数量)",
            "alarmCount (总告警数量)",
            "alarmType_list (告警类型列表)",
            "unclearedAlarmCount_H (H侧未清除告警数量)",
            "zeroNegotiationRxRateCnt (协商接收速率为0的次数)",
            "zeroNegotiationTxRatePercent (协商发送速率为0的占比)",
            "zeroAchievableRateCnt (可达速率等于0的次数)",
            "zeroAchievableRatePercent (可达速率等于0的占比)",
        ],
        "interruption_week_ave (周平均中断时长扣分)": [
            "unclearedAlarmCount_A (A侧未清除告警数量)",
            "alarmCount (总告警数量)",
            "alarmType_list (告警类型列表)",
            "unclearedAlarmCount_H (H侧未清除告警数量)",
            "zeroNegotiationRxRateCnt (协商接收速率为0的次数)",
            "zeroNegotiationTxRatePercent (协商发送速率为0的占比)",
            "zeroAchievableRateCnt (可达速率等于0的次数)",
            "zeroAchievableRatePercent (可达速率等于0的占比)",
        ],
        "Stability_score (稳定性维度得分)": [
            "unclearedAlarmCount_A (A侧未清除告警数量)",
            "alarmCount (总告警数量)",
            "alarmType_list (告警类型列表)",
            "unclearedAlarmCount_H (H侧未清除告警数量)",
            "zeroNegotiationRxRateCnt (协商接收速率为0的次数)",
            "zeroNegotiationTxRatePercent (协商发送速率为0的占比)",
            "zeroAchievableRateCnt (可达速率等于0的次数)",
            "zeroAchievableRatePercent (可达速率等于0的占比)",
        ],
    },
    "ODN": {
        "oltRxPowerHighCnt (OLT接收光功率异常次数)": [
            "oltRxPowerHigh (OLT接收光功率异常标记)",
            "oltRxWeakLight (OLT接收弱光指示)",
        ],
        "oltRxPowerCnt (OLT接收光功率采集次数)": [
            "RxPower (接收光功率)",
        ],
        "bipHighCnt (BIP误码率越限次数)": [
            "bipHigh (BIP误码数超过阈值的标记)",
        ],
        "bipCnt (BIP误码率采集次数)": [
            "ontDownstreamBipErrors (ONT下行BIP误码数)",
        ],
        "fecHighCnt (FEC错帧率越限次数)": [
            "fecHigh (FEC错帧数超过阈值的标记)",
        ],
        "oltRxPowerPercent (OLT接收光功率越限占比)": [
            "oltRxWeakLight (OLT接收弱光指示)",
            "oltRxPowerHigh (OLT接收光功率异常标记)",
            "RxPower (接收光功率)",
        ],
        "bipPercent (BIP误码率越限占比)": [
            "bipHigh (BIP误码数超过阈值的标记)",
            "ontDownstreamBipErrors (ONT下行BIP误码数)",
        ],
        "fecPercent (FEC错帧率越限占比)": [
            "fecHigh (FEC错帧数超过阈值的标记)",
            "ontRxFecErrors (ONT接收FEC错帧数)",
        ],
        "oltRxPowerScore (OLT接收光功率越限占比扣分)": [
            "oltRxWeakLight (OLT接收弱光指示)",
            "oltRxPowerHigh (OLT接收光功率异常标记)",
            "RxPower (接收光功率)",
        ],
        "bipScore (BIP越限占比扣分)": [
            "bipHigh (BIP误码数超过阈值的标记)",
            "ontDownstreamBipErrors (ONT下行BIP误码数)",
        ],
        "fecScore (FEC越限占比扣分)": [
            "fecHigh (FEC错帧数超过阈值的标记)",
            "ontRxFecErrors (ONT接收FEC错帧数)",
        ],
        "ODN_score (ODN维度得分)": [
            "ontRxFecErrors (ONT接收FEC错帧数)",
            "bipHigh (BIP误码数超过阈值的标记)",
            "fecHigh (FEC错帧数超过阈值的标记)",
            "ontDownstreamBipErrors (ONT下行BIP误码数)",
            "oltRxWeakLight (OLT接收弱光指示)",
            "oltRxPowerHigh (OLT接收光功率异常标记)",
            "RxPower (接收光功率)",
        ],
    },
    "Rate": {
        "maxTxRateHighCnt (pon口到ont方向下行最大速率越限次数)": [
            "maxTxTraffic (pon口到ont方向最大下行流量（单位：KB）)",
        ],
        "meanRxRateHighCnt (ont到pon口方向上行平均速率越限次数)": [
            "meanRxTraffic (ont到pon口方向平均上行流量（单位：KB）)",
        ],
        "peakRxRateHighCnt (ont到pon口方向上行峰值速率越限次数)": [
            "peakRxRateHigh (ont到pon口方向上行峰值速率超过阈值的标记)",
            "peakRxRate (ont到pon口方向上行峰值速率)",
        ],
        "rxTrafficHighCnt (ont到pon口方向上行流量越限次数)": [
            "meanRxTraffic (ont到pon口方向平均上行流量（单位：KB）)",
        ],
        "isTxTrafficHighCnt (pon口到ont方向下行流量等于0次数)": [
            "maxTxTraffic (pon口到ont方向最大下行流量（单位：KB）)",
        ],
        "isRxTrafficHighCnt (ont到pon口方向上行流量等于0次数)": [
            "meanRxTraffic (ont到pon口方向平均上行流量（单位：KB）)",
        ],
        "isTxTrafficPercent (pon口到ont方向下行流量等于0占比)": [
            "maxTxTraffic (pon口到ont方向最大下行流量（单位：KB）)",
        ],
        "isRxTrafficPercent (ont到pon口方向上行流量等于0占比)": [
            "meanRxTraffic (ont到pon口方向平均上行流量（单位：KB）)",
        ],
        "maxTxRateHighCntPercent (pon口到ont方向下行最大速率越限占比)": [
            "maxTxTraffic (pon口到ont方向最大下行流量（单位：KB）)",
        ],
        "peakRxRatePercent (ont到pon口方向上行上行峰值速率越限占比)": [
            "peakRxRateHigh (ont到pon口方向上行峰值速率超过阈值的标记)",
            "peakRxRate (ont到pon口方向上行峰值速率)",
        ],
        "maxTxRatePercent (pon口到ont方向下行最大速率异常比例)": [
            "maxTxTraffic (pon口到ont方向最大下行流量（单位：KB）)",
        ],
        "meanRxRatePercent (ont到pon口方向上行平均速率异常比例)": [
            "meanRxTraffic (ont到pon口方向平均上行流量（单位：KB）)",
        ],
        "rxTrafficPercent (ont到pon口方向上行流量异常比例)": [
            "meanRxTraffic (ont到pon口方向平均上行流量（单位：KB）)",
        ],
    },
    "Service": {
        "officeDepressionTimesPercent (办公大类质差时长占比)": [
            "officePoorQualityCount (办公类应用业务质差次数)",
        ],
        "gameDepressionTimesPercent (游戏大类质差时长占比)": [
            "gamePoorQualityCount (游戏类应用业务质差次数)",
        ],
        "videoCallDepressionTimesPercent (视频通话类质差时长占比)": [
            "videoCallPoorQualityCount (视频通话类应用业务质差次数)",
        ],
        "educationDepressionTimesPercent (教育类质差时长占比)": [
            "educationPoorQualityCount (教育类应用业务质差次数)",
        ],
        "liveVideoDepressionTimesPercent (直播类质差时长占比)": [
            "liveVideoPoorQualityCount (直播视频类应用业务质差次数)",
        ],
        "anchorVideoDepressionTimesPercent (主播类质差时长占比)": [
            "anchorVideoPoorQualityCount (主播视频类应用业务质差次数)",
        ],
        "pointVideoDepressionTimesPercent (点播类质差时长占比)": [
            "pointVideoPoorQualityCount (点播视频类应用业务质差次数)",
        ],
        "generalTcpDepressionTimesPercent (通用TCP类质差时长占比)": [
            "generalTcpPoorQualityCount (通用TCP类应用业务质差次数)",
        ],
    },
    "OLT": {
        "G10UpPlrHighCnt (10GPON丢包率越限次数)": [
            "G10UpPlrHigh (10GPON端口上行丢包率超过阈值的标记)",
            "G10UpPlr (10GPON端口上行丢包率)",
        ],
        "G1UpPlrHighCnt (GPON丢包率越限次数)": [
            "G1UpPlrHigh (GPON端口上行丢包率超过阈值的标记)",
            "G1UpPlr (GPON端口上行丢包率)",
        ],
        "portUpPlrHighCnt (端口发送丢包率越限次数)": [
            "portUpPlrHigh (端口上行丢包率超过阈值的标记)",
            "portUpPlr (端口上行丢包率)",
        ],
        "G10UpPlrPercent (10GPON丢包率越限占比)": [
            "G10UpPlrHigh (10GPON端口上行丢包率超过阈值的标记)",
            "G10TxPacketCount (10GPON端口发送数据包总数)",
            "G10UpPlr (10GPON端口上行丢包率)",
        ],
        "G1UpPlrPercent (GPON丢包率越限占比)": [
            "G1UpPlrHigh (GPON端口上行丢包率超过阈值的标记)",
            "G1TxPacketCount (GPON发送数据包总数)",
            "G1UpPlr (GPON端口上行丢包率)",
        ],
        "portUpPlrPercent (端口丢包率越限占比)": [
            "portUpPlrHigh (端口上行丢包率超过阈值的标记)",
            "portTxPacketCount (端口发送数据包总数)",
            "portUpPlr (端口上行丢包率)",
        ],
        "portUpPlrScore (端口丢包率越限扣分)": [
            "portUpPlrHigh (端口上行丢包率超过阈值的标记)",
            "portTxPacketCount (端口发送数据包总数)",
            "portUpPlr (端口上行丢包率)",
        ],
        "G1UpPlrScore (GPON丢包率越限扣分)": [
            "G1UpPlrHigh (GPON端口上行丢包率超过阈值的标记)",
            "G1TxPacketCount (GPON发送数据包总数)",
            "G1UpPlr (GPON端口上行丢包率)",
        ],
        "G10UpPlrScore (10GPON丢包率越限扣分)": [
            "G10UpPlrHigh (10GPON端口上行丢包率超过阈值的标记)",
            "G10TxPacketCount (10GPON端口发送数据包总数)",
            "G10UpPlr (10GPON端口上行丢包率)",
        ],
        "OLT_score (OLT维度得分)": [
            "G10UpPlrHigh (10GPON端口上行丢包率超过阈值的标记)",
            "G10TxPacketCount (10GPON端口发送数据包总数)",
            "G10UpPlr (10GPON端口上行丢包率)",
            "G1UpPlrHigh (GPON端口上行丢包率超过阈值的标记)",
            "G1TxPacketCount (GPON发送数据包总数)",
            "G1UpPlr (GPON端口上行丢包率)",
            "portUpPlrHigh (端口上行丢包率超过阈值的标记)",
            "portTxPacketCount (端口发送数据包总数)",
            "portUpPlr (端口上行丢包率)",
        ],
    },
    "Gateway": {
        "apExceHighCnt (从网关连接异常次数)": [
            "apExceHighCnt (从网关异常连接超过阈值的次数)",
            "apWifiHighCnt (从网关Wi-Fi连接质量差的次数)",
            "apLanHighCnt (从网关LAN连接异常次数)",
            "apPonHighCnt (从网关光纤连接异常次数)",
        ],
        "apWifiHighCnt (从网关连接方式为Wi-Fi异常次数)": [
            "apWifiHighCnt (从网关Wi-Fi连接质量差的次数)",
        ],
        "apLanHighCnt (从网关连接方式为LAN异常次数)": [
            "apLanHighCnt (从网关LAN连接异常次数)",
        ],
        "apPonHighCnt (从网关连接方式为光纤异常次数)": [
            "apPonHighCnt (从网关光纤连接异常次数)",
        ],
        "homeRamHighCnt (主网关内存占用越限次数)": [
            "homeRamHigh (主网关内存占用率超过阈值的标记)",
            "homeRamMax (主网关最大内存占用率)",
        ],
        "apRamHighCnt (从网关内存占用越限次数)": [
            "apRamHigh (从网关内存占用率超过阈值的标记)",
            "apRamMax (从网关最大内存占用率)",
        ],
        "homeCpuMaxHighCnt (主网关CPU使用率最大值越限次数)": [
            "homeCpuMaxHigh (主网关CPU使用率超过阈值的标记)",
            "homeCpuMax (主网关最大CPU使用率)",
        ],
        "apCpuMaxHighCnt (从网关CPU使用率最大值越限次数)": [
            "apCpuMaxHigh (从网关CPU使用率超过阈值的标记)",
            "apCpuMax (从网关最大CPU使用率)",
        ],
        "ramScore (内存占用越限扣分)": [
            "homeRamHigh (主网关内存占用率超过阈值的标记)",
            "homeRamMax (主网关最大内存占用率)",
            "apRamHigh (从网关内存占用率超过阈值的标记)",
            "apRamMax (从网关最大内存占用率)",
        ],
        "cpuMaxScore (CPU使用率越限扣分)": [
            "homeCpuMaxHigh (主网关CPU使用率超过阈值的标记)",
            "homeCpuMax (主网关最大CPU使用率)",
            "apCpuMaxHigh (从网关CPU使用率超过阈值的标记)",
            "apCpuMax (从网关最大CPU使用率)",
        ],
        "apExceScore (主从连接异常扣分)": [
            "apExceHighCnt (从网关异常连接超过阈值的次数)",
            "apWifiHighCnt (从网关Wi-Fi连接质量差的次数)",
            "apLanHighCnt (从网关LAN连接异常次数)",
            "apPonHighCnt (从网关光纤连接异常次数)",
            "apLanCnt (从网关LAN连接总次数)",
            "apWifiCnt (从网关Wi-Fi连接总次数)",
            "apPonCnt (从网关光纤连接总次数)",
        ],
        "Gateway_score (网关维度得分)": [
            "homeRamHigh (主网关内存占用率超过阈值的标记)",
            "homeRamMax (主网关最大内存占用率)",
            "apRamHigh (从网关内存占用率超过阈值的标记)",
            "apRamMax (从网关最大内存占用率)",
            "homeCpuMaxHigh (主网关CPU使用率超过阈值的标记)",
            "homeCpuMax (主网关最大CPU使用率)",
            "apCpuMaxHigh (从网关CPU使用率超过阈值的标记)",
            "apCpuMax (从网关最大CPU使用率)",
            "apExceHighCnt (从网关异常连接超过阈值的次数)",
            "apWifiHighCnt (从网关Wi-Fi连接质量差的次数)",
            "apLanHighCnt (从网关LAN连接异常次数)",
            "apPonHighCnt (从网关光纤连接异常次数)",
            "apLanCnt (从网关LAN连接总次数)",
            "apWifiCnt (从网关Wi-Fi连接总次数)",
            "apPonCnt (从网关光纤连接总次数)",
        ],
    },
    "STA": {
        "allAntennaCnt (有天线终端数量)": [
            "numLanWiredDevices (连接有线LAN设备数量)",
        ],
        "midSatisfactionStaCnt (带宽满意度为中的数量)": [
            "avgAchievableRate (平均可达速率)",
            "numSTA (STA设备数量)",
            "avgNegotiationTxRate (平均协商发送速率)",
            "avgNegotiationRxRate (平均接收协商速率)",
        ],
        "allSatisfactionStaCnt (可计算终端满意度的终端数量)": [
            "numSTA (STA设备数量)",
        ],
        "lowSatisfactionStaCnt (带宽满意度为低的数量)": [
            "avgAchievableRate (平均可达速率)",
            "numSTA (STA设备数量)",
            "avgNegotiationTxRate (平均协商发送速率)",
            "avgNegotiationRxRate (平均接收协商速率)",
        ],
        "isAchievableRateHighCnt (可达速率等于0次数)": [
            "zeroAchievableRateCnt (可达速率等于0的次数)",
            "avgAchievableRate (平均可达速率)",
        ],
        "isAchievableRatePercent (可达速率等于0占比)": [
            "zeroAchievableRatePercent (可达速率等于0的占比)",
            "zeroAchievableRateCnt (可达速率等于0的次数)",
            "avgAchievableRate (平均可达速率)",
        ],
        "lowSatisfactionStaScore (带宽满意度为低扣分)": [
            "avgAchievableRate (平均可达速率)",
            "numSTA (STA设备数量)",
            "avgNegotiationTxRate (平均协商发送速率)",
            "avgNegotiationRxRate (平均接收协商速率)",
        ],
        "midSatisfactionStaScore (带宽满意度为中扣分)": [
            "avgAchievableRate (平均可达速率)",
            "numSTA (STA设备数量)",
            "avgNegotiationTxRate (平均协商发送速率)",
            "avgNegotiationRxRate (平均接收协商速率)",
        ],
        "isAchievableRateScore (可达速率等于0扣分)": [
            "zeroAchievableRatePercent (可达速率等于0的占比)",
            "zeroAchievableRateCnt (可达速率等于0的次数)",
            "avgAchievableRate (平均可达速率)",
        ],
        "STA_score (终端维度得分)": [
            "avgAchievableRate (平均可达速率)",
            "numSTA (STA设备数量)",
            "avgNegotiationTxRate (平均协商发送速率)",
            "avgNegotiationRxRate (平均接收协商速率)",
            "zeroAchievableRatePercent (可达速率等于0的占比)",
            "zeroAchievableRateCnt (可达速率等于0的次数)",
        ],
    },
    "Wifi": {
        "radioTypeCnt (Wi-Fi频段数据采集次数)": [
            "apWifiCnt (从网关Wi-Fi连接总次数)",
        ],
        "device5MinNumHighCnt (五分钟下挂设备数量越限次数)": [
            "totalDevices (总设备数量)",
        ],
        "diagLossHighCnt (Ping丢包率越限次数)": [
            "diagLossHigh (丢包率超过阈值的标记)",
            "maxDiagLossRate (最大空口丢包率)",
            "avgDownLossRate (平均下行丢包率)",
            "avgDiagLossRate (平均空口丢包率)",
        ],
        "diagTimeDelayHighCnt (Ping时延越限次数)": [
            "maxDiagMaxTime (最大空口时延)",
            "minDiagMinTime (最小空口时延)",
            "avgDiagAvgTime (平均空口时延)",
        ],
        "roamDelayCnt (漫游切换时延越限次数)": [
            "roamDelayHigh (漫游切换时延超过阈值的标记)",
        ],
        "emptyDelayCnt (空口时延越限次数)": [
            "diagTimeDelayHigh (空口时延超过阈值的标记)",
            "maxDiagMaxTime (最大空口时延)",
            "minDiagMinTime (最小空口时延)",
            "avgDiagAvgTime (平均空口时延)",
        ],
        "deviceNumCnt (五分钟下挂设备数量)": [
            "totalDevices (总设备数量)",
        ],
        "midInterferencePercent (干扰空占比中分箱区间占比)": [
            "midCnt (Wi-Fi中等干扰次数)",
            "sumTotal (Wi-Fi总干扰评估次数)",
        ],
        "highInterferencePercent (干扰空占比高分箱区间占比)": [
            "highCnt (Wi-Fi高干扰次数)",
            "sumTotal (Wi-Fi总干扰评估次数)",
        ],
        "lowInterferencePercent (干扰空占比低分箱区间占比)": [
            "lowCnt (Wi-Fi低干扰次数)",
            "sumTotal (Wi-Fi总干扰评估次数)",
        ],
        "diagLossPercent (Ping丢包率越限占比)": [
            "diagLossHigh (丢包率超过阈值的标记)",
            "maxDiagLossRate (最大空口丢包率)",
            "avgDownLossRate (平均下行丢包率)",
            "avgDiagLossRate (平均空口丢包率)",
        ],
        "dBmPercent (WIFI信号强度平均越限占比)": [
            "avgWifiSignal (平均Wi-Fi信号强度)",
            "avgNoise (平均Wi-Fi信号噪声值)",
            "avgSnr (平均信噪比)",
            "dBmPercent (Wi-Fi信号强度弱占比)",
        ],
        "roamDelayPercent (漫游时延越限占比)": [
            "roamDelayHigh (漫游切换时延超过阈值的标记)",
        ],
        "emptyDelayPercent (空口时延越限占比)": [
            "diagTimeDelayHigh (空口时延超过阈值的标记)",
            "maxDiagMaxTime (最大空口时延)",
            "minDiagMinTime (最小空口时延)",
            "avgDiagAvgTime (平均空口时延)",
        ],
        "dBmScore (信号强度不足扣分)": [
            "avgWifiSignal (平均Wi-Fi信号强度)",
            "avgNoise (平均Wi-Fi信号噪声值)",
            "avgSnr (平均信噪比)",
        ],
        "diagTimeDelayScore (空口时延越限扣分)": [
            "diagTimeDelayHigh (空口时延超过阈值的标记)",
            "maxDiagMaxTime (最大空口时延)",
            "minDiagMinTime (最小空口时延)",
            "avgDiagAvgTime (平均空口时延)",
        ],
        "roamDelayScore (漫游时延越限扣分)": [
            "roamDelayHigh (漫游切换时延超过阈值的标记)",
        ],
        "lowInterferenceScore (干扰占空比低区间扣分)": [
            "lowCnt (Wi-Fi低干扰次数)",
            "sumTotal (Wi-Fi总干扰评估次数)",
        ],
        "midInterferenceScore (干扰占空比中区间扣分)": [
            "midCnt (Wi-Fi中等干扰次数)",
            "sumTotal (Wi-Fi总干扰评估次数)",
        ],
        "highInterferenceScore (干扰占空比高区间扣分)": [
            "highCnt (Wi-Fi高干扰次数)",
            "sumTotal (Wi-Fi总干扰评估次数)",
        ],
    },
}


def _extract_field_name(field_with_desc: str) -> str:
    """从 'fieldName (描述)' 格式中提取纯字段名"""
    match = re.match(r"^(\S+)", field_with_desc)
    return match.group(1) if match else field_with_desc


def get_minute_fields_for_dimension(dimension: str) -> list[str]:
    """获取某个维度对应的所有分钟表字段名（去重，纯字段名）"""
    dim_key = _normalize_dimension(dimension)
    if dim_key not in DIMENSION_FIELD_MAPPING:
        return []
    fields = set()
    for minute_fields in DIMENSION_FIELD_MAPPING[dim_key].values():
        for f in minute_fields:
            fields.add(_extract_field_name(f))
    return sorted(fields)


def get_all_minute_fields() -> set[str]:
    """获取所有分钟表字段名集合（纯字段名）"""
    fields = set()
    for dim_mapping in DIMENSION_FIELD_MAPPING.values():
        for minute_fields in dim_mapping.values():
            for f in minute_fields:
                fields.add(_extract_field_name(f))
    return fields


def get_minute_schema(focus_dimensions: list[str]) -> str:
    """
    根据 focus_dimensions 生成分钟表 schema（天表→分钟表映射关系）。
    focus_dimensions 可以是维度名（如 "Stability"）或字段名（如 "diagLossHigh"）。
    如果全部匹配不上，输出全量映射表（不能让 LLM 只看到裸字段列表）。
    """
    parts = [
        "## 分钟表核心分组字段",
        "- portUuid: PON口ID",
        "- time_id: 分钟级时间戳（ORDERED类型，用于时序分析）",
        "- gatewayMac: ONT设备MAC地址",
        "",
    ]

    # 将 focus_dimensions 归一化为维度名集合
    resolved_dims: set[str] = set()
    if focus_dimensions:
        for dim in focus_dimensions:
            dim_key = _normalize_dimension(dim)
            if dim_key in DIMENSION_FIELD_MAPPING:
                resolved_dims.add(dim_key)

    # 如果一个都没匹配上（传入的是字段名而非维度名），输出全量映射
    if not resolved_dims:
        if focus_dimensions:
            logger.warning("focus_dimensions %s 无法匹配任何维度，输出全量映射表", focus_dimensions)
        resolved_dims = set(DIMENSION_FIELD_MAPPING.keys())

    for dim_key in sorted(resolved_dims):
        parts.append(f"## {dim_key} 维度：天表字段 → 分钟表字段映射")
        parts.append("（天表字段有异常时，可下钻查对应的分钟表字段）\n")

        for day_field, minute_fields in DIMENSION_FIELD_MAPPING[dim_key].items():
            minute_list = ", ".join(minute_fields)
            parts.append(f"- {day_field} → {minute_list}")
        parts.append("")

    # 追加所有可用分钟表字段名列表，硬约束 LLM 只能使用这些字段
    all_fields = sorted(get_all_minute_fields())
    parts.append(
        "🔴🔴🔴 以下是分钟表全部合法字段名。measures.name 只能从此列表选取！使用列表外的字段（如天表的 linkFlapCnt、oltRxPowerHighCnt 等）将导致查询失败！🔴🔴🔴"
    )
    parts.append(", ".join(all_fields))
    parts.append("")

    return "\n".join(parts)


# 反向索引：分钟表字段名 → 所属维度名
_FIELD_TO_DIMENSION: dict[str, str] = {}


def _build_field_to_dimension():
    """构建字段→维度的反向索引"""
    if _FIELD_TO_DIMENSION:
        return
    for dim_key, day_fields in DIMENSION_FIELD_MAPPING.items():
        for day_field, minute_fields in day_fields.items():
            # 天表字段名也映射到维度
            day_name = _extract_field_name(day_field)
            _FIELD_TO_DIMENSION[day_name] = dim_key
            _FIELD_TO_DIMENSION[day_name.lower()] = dim_key
            # 分钟表字段名也映射到维度
            for mf in minute_fields:
                mf_name = _extract_field_name(mf)
                _FIELD_TO_DIMENSION[mf_name] = dim_key
                _FIELD_TO_DIMENSION[mf_name.lower()] = dim_key


def _normalize_dimension(dim: str) -> str:
    """
    将维度名归一化为 DIMENSION_FIELD_MAPPING 的 key。
    支持：维度名（"Stability"）、带_score后缀（"Stability_score"）、字段名（"diagLossHigh"）
    """
    dim = dim.strip().replace("_score", "")
    # 直接匹配维度名
    if dim in DIMENSION_FIELD_MAPPING:
        return dim
    # 大小写不敏感匹配
    for key in DIMENSION_FIELD_MAPPING:
        if dim.lower() == key.lower():
            return key
    # 字段名反查维度
    _build_field_to_dimension()
    if dim in _FIELD_TO_DIMENSION:
        return _FIELD_TO_DIMENSION[dim]
    if dim.lower() in _FIELD_TO_DIMENSION:
        return _FIELD_TO_DIMENSION[dim.lower()]
    return dim
