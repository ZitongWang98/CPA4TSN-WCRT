# ATS 分析的停止条件与理论表述

## 问题背景

标准 CPA busy window 框架：
- `b_plus(q)` 是处理 q 个 activation 的**累积 busy window**
- 停止条件：`δ_min(q+1) ≥ b_plus(q)` → busy period 结束
- WCRT = max_q { b_plus(q) - δ_min(q) }

ATS Eq.(3.42) 中 `w_q = eT_block(q) + LPB + SPB + HPB(w̃_q)` 是第 q 帧**独立的等待时间**，不是累积 busy window。每个 q 的 LPB、SPB 都是独立最坏情况（eT 等待结束时刻恰好碰到 LP/SP 帧）。

两者不兼容：per-q 独立分析下 b_plus(q) 不收敛于 δ_min(q+1)，标准停止条件永远不满足。

## 根本原因

ATS 的 eT_block 是 per-frame 的调度机制阻塞，把 busy window "打断"了。eT 等待期间 HP/SP/LP 均不造成阻塞（论文已说明），因此 HPB 窗口不连续，无法用 η⁺ 对整个 busy window 一次性计算。

## 实现方案

采用 per-activation worst-case analysis：

```
R_q = eT_block(q) + LPB + SPB + HPB(w̃_q) + C_i
其中 w̃_q = LPB + SPB + HPB(w̃_q) 为不动点
WCRT = max_q { R_q }
停止条件：R_{q+1} ≤ R_q 时终止遍历
```

代码中 `b_plus(q) = δ_min(q) + R_q`，`response_time(q) = b_plus(q) - δ_min(q) = R_q`。

## 停止条件的正确性论证

1. eT_block(q) 由令牌恢复决定，当 q 足够大时进入稳态（令牌恢复模式固定，interval = δ_min(q) - δ_min(q-1) 趋于常数）
2. LPB、SPB 对每个 q 相同（均为常数）
3. HPB(w̃_q) 中 w̃_q = LPB + SPB + HPB(w̃_q) 不依赖 q，因此 HPB 也是常数
4. 故 R_q 在 eT_block 稳态后为常数，R_{q+1} = R_q，遍历终止
5. WCRT = max(R_1, R_2, ..., R_steady)，有限步内可达

## 论文补充建议

在 Eq.(3.42) 后补充：

> 由于 ATS 调度机制阻塞是逐帧独立的，与标准严格优先级的累积繁忙窗口不同，ATS 流的 WCRT 需要遍历所有可能的 q 取最大响应时间。当令牌恢复进入稳态后（即 eT_block(q) 不再变化），R_q 不再增长，遍历终止。因此：
>
> WCRT_i = max_q { R_{i,q} }
>
> 其中 R_{i,q} = eT_block(i,q) + LPB_i + SPB_i + HPB_i(w̃) + C_i

## 相关代码

- `schedulers_ats.py` → `ATSScheduler.stopping_condition()`
- 实现：`rt_next <= rt_cur` 即 `R_{q+1} ≤ R_q`
