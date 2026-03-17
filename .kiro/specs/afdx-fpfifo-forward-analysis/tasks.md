# 实现计划：AFDX FP/FIFO 前向端到端延迟分析

## 概述

将设计文档中的 AFDX FP/FIFO 前向分析方法转化为可执行的编码任务。实现顺序为：数据结构 → 输入验证 → 核心算法（逐跳分析） → 公共 API → 薄封装层 → 示例脚本 → 测试。每个任务在前一个任务基础上递增构建，确保无孤立代码。

## 任务

- [x] 1. 实现核心数据结构与输入验证
  - [x] 1.1 在 `forward_analysis/fa_fpfifo.py` 中创建 HopResult 和 AnalysisResult 数据类
    - 创建 `forward_analysis/fa_fpfifo.py` 文件
    - 实现 `HopResult` dataclass，包含字段：hop_index、resource_name、task_name、smax、smin、wcrt
    - 实现 `AnalysisResult` dataclass，包含字段：path、path_name、hop_results、e2e_wcrt、smax_initial、smin_initial
    - 导入 pycpa.model 模块
    - _需求：7.1, 7.2_

  - [x] 1.2 实现 `_validate_path` 输入验证方法
    - 在 `FPFIFOForwardAnalyzer` 类骨架中实现 `_validate_path(self, path)` 方法
    - 检查 Task 是否绑定 Resource，未绑定则抛出 ValueError
    - 检查首个非 ForwardingTask 的 Task 是否设置 in_event_model，未设置则抛出 ValueError
    - 检查 Task 的 wcet 是否 > 0，否则抛出 ValueError
    - 检查 Task 是否设置 scheduling_parameter，未设置则抛出 ValueError
    - 检查过滤 ForwardingTask 后是否有可分析任务，无则抛出 ValueError
    - 错误信息格式遵循设计文档中的错误处理表
    - _需求：8.1, 8.2, 8.3, 8.4_

  - [x] 1.3 实现 `_get_analysis_tasks` 和 `_get_technological_latency` 辅助方法
    - 实现 `_get_analysis_tasks(self, path)` 方法，从 Path.tasks 中过滤掉 ForwardingTask 实例
    - 实现 `_get_technological_latency(self, resource)` 方法，读取 Resource 的 forwarding_delay 属性，默认返回 0
    - _需求：1.2, 5.1, 5.2, 5.3_

- [x] 2. 实现单跳 FP/FIFO 延迟计算核心算法
  - [x] 2.1 实现 `_init_smax_smin` 初始化方法
    - 实现 `_init_smax_smin(self, task)` 方法
    - 从首个 Task 的 in_event_model 读取 P（周期/BAG）和 J（初始抖动）
    - 初始化 Smax_0 = J，Smin_0 = 0
    - _需求：4.1_

  - [x] 2.2 实现 `_compute_hp_interference` 高优先级干扰计算
    - 实现 `_compute_hp_interference(self, task, smax_map, smin_map)` 方法
    - 遍历同一 Resource 上所有 scheduling_parameter 数值更小（优先级更高）的 Task
    - 跳过 ForwardingTask 实例
    - 使用不动点迭代计算 HP 干扰量：`Σ_j ceil((R + J_j^h) / P_j) * C_j`
    - 其中 `J_j^h = Smax_j^{h-1} - Smin_j^{h-1}`
    - 设置最大迭代次数 1000，超过则抛出 RuntimeError
    - _需求：2.1_

  - [x] 2.3 实现 `_compute_sp_fifo_interference` 同优先级 FIFO 干扰计算
    - 实现 `_compute_sp_fifo_interference(self, task, smax_map, smin_map, with_serialization)` 方法
    - 遍历同一 Resource 上所有 scheduling_parameter 相同的 Task（排除自身）
    - 跳过 ForwardingTask 实例
    - 不启用序列化时：`Σ_j min(ceil((Smax_j - Smin_i + ε) / P_j), 1+floor(J_j/P_j)) * C_j`
    - 启用序列化时：扣除来自同一输入端口的帧的序列化约束
    - _需求：2.2, 3.1, 3.2, 3.3_

  - [x] 2.4 实现 `_compute_lp_blocking` 低优先级阻塞计算
    - 实现 `_compute_lp_blocking(self, task)` 方法
    - 遍历同一 Resource 上所有 scheduling_parameter 数值更大（优先级更低）的 Task
    - 跳过 ForwardingTask 实例
    - 返回所有低优先级流中最大的 wcet 值，无低优先级流则返回 0
    - _需求：2.3_

  - [x] 2.5 实现 `_compute_single_hop_wcrt` 单跳 WCRT 组合计算
    - 实现 `_compute_single_hop_wcrt(self, task, smax_map, smin_map, with_serialization)` 方法
    - 组合：wcrt = C_i + HP_interference + SP_FIFO_interference + LP_blocking
    - 其中 C_i 为 task.wcet
    - 调用 2.2、2.3、2.4 中实现的方法
    - _需求：2.4_

- [x] 3. 检查点 - 确保核心算法实现完整
  - 确保所有核心计算方法已实现且逻辑正确，如有疑问请询问用户。

- [x] 4. 实现公共 API 与逐跳前向传播
  - [x] 4.1 实现 `analyze_path` 方法（逐跳前向传播）
    - 实现 `FPFIFOForwardAnalyzer.analyze_path(self, path, with_serialization=False)` 方法
    - 调用 `_validate_path` 验证输入
    - 调用 `_get_analysis_tasks` 获取可分析任务列表
    - 第一轮：为所有 Path 的所有 Task 初始化 Smax/Smin 映射表（使用 `_init_smax_smin`）
    - 第二轮：逐跳前向传播
      - 对每一跳调用 `_compute_single_hop_wcrt` 计算 wcrt
      - 更新 Smax：`Smax_new = Smax_prev + wcrt + tech_latency`
      - 更新 Smin：`Smin_new = Smin_prev + bcet + tech_latency`
      - 创建 HopResult 记录
    - 计算 e2e_wcrt = Smax_last - Smin_initial
    - 返回 AnalysisResult 对象
    - _需求：1.5, 2.4, 2.5, 2.6, 4.1, 4.2, 4.3, 4.4, 6.2, 6.3, 7.1, 7.2_

  - [x] 4.2 实现 `analyze_all` 方法
    - 实现 `FPFIFOForwardAnalyzer.analyze_all(self, with_serialization=False)` 方法
    - 两轮策略：先为所有 Path 的所有 Task 初始化 Smax/Smin，再逐跳传播
    - 遍历 system 中所有已注册 Path，对每条 Path 调用分析逻辑
    - 返回 Dict[Path, AnalysisResult]
    - System 无已注册 Path 时返回空字典
    - _需求：6.1, 7.3_

  - [x] 4.3 实现 `print_results` 方法
    - 实现 `FPFIFOForwardAnalyzer.print_results(self, results=None)` 方法
    - 以可读格式打印每条 VL 的逐跳延迟和端到端延迟
    - 若 results 为 None 则打印最近一次 analyze_all 的结果
    - _需求：6.4_

  - [x] 4.4 实现 `__init__` 构造函数
    - 实现 `FPFIFOForwardAnalyzer.__init__(self, system)` 构造函数
    - 存储 system 引用
    - 初始化内部状态（smax_map、smin_map、最近结果缓存）
    - _需求：1.1_

- [x] 5. 实现薄封装层与模块导出
  - [x] 5.1 创建 `forward_analysis/analyzer.py` 薄封装层
    - 创建 `forward_analysis/analyzer.py` 文件
    - 从 `.fa_fpfifo` 导入 `FPFIFOForwardAnalyzer`、`HopResult`、`AnalysisResult`
    - 重新导出这些类，使 `__init__.py` 的 `from .analyzer import FPFIFOForwardAnalyzer` 正常工作
    - _需求：10.2, 10.3, 10.4_

- [x] 6. 检查点 - 确保模块可导入且 API 完整
  - 确保 `from forward_analysis import FPFIFOForwardAnalyzer` 可正常工作，所有公共方法可调用，如有疑问请询问用户。

- [x] 7. 实现示例脚本
  - [x] 7.1 创建 `examples/afdx_forward_analysis/example_fpfifo.py` 示例脚本
    - 创建示例脚本文件
    - 使用 pycpa 的 System、Resource、Task、Path、PJdEventModel 构建与论文一致的 AFDX 网络拓扑
    - 调用 `FPFIFOForwardAnalyzer.analyze_all` 执行前向分析
    - 打印每条 VL 的逐跳分析结果和端到端延迟
    - 将分析结果与论文参考值对比并输出对比结果
    - _需求：9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 8. 实现属性测试与单元测试
  - [x] 8.1 在 `test/test_fa_fpfifo.py` 中创建 Hypothesis 生成器策略
    - 创建 `test/test_fa_fpfifo.py` 文件
    - 使用 Hypothesis 的 `@composite` 策略构建有效的 pycpa 模型对象生成器
    - 生成随机 AFDX 网络配置：交换机数量、VL 数量、优先级分配、帧大小、BAG 值
    - 确保生成配置满足基本约束：bcet ≤ wcet, wcet > 0, P > 0
    - 覆盖边界情况：单跳路径、单流网络、所有流同优先级、无低优先级流
    - _需求：全部_

  - [ ]* 8.2 编写属性测试：Smax ≥ Smin 不变量
    - **属性 1：Smax ≥ Smin invariant**
    - **验证需求：2.4, 2.5, 2.6**

  - [ ]* 8.3 编写属性测试：Smax 和 Smin 沿路径单调非递减
    - **属性 2：Smax and Smin monotonically non-decreasing along path**
    - **验证需求：2.5, 2.6, 4.2**

  - [ ]* 8.4 编写属性测试：端到端延迟等于 Smax_last - Smin_initial
    - **属性 3：e2e_wcrt = Smax_last - Smin_initial**
    - **验证需求：4.3**

  - [ ]* 8.5 编写属性测试：端到端延迟下界
    - **属性 4：e2e_wcrt >= sum(bcet) + sum(tech_latency)**
    - **验证需求：2.4, 4.3, 4.4**

  - [ ]* 8.6 编写属性测试：序列化效应单调性
    - **属性 5：serialization delay <= non-serialization delay**
    - **验证需求：3.1**

  - [ ]* 8.7 编写属性测试：所有结果非负
    - **属性 6：all results non-negative**
    - **验证需求：2.4, 2.5, 2.6, 4.3**

  - [ ]* 8.8 编写属性测试：分析确定性
    - **属性 7：analysis is deterministic**
    - **验证需求：6.1, 6.2**

  - [ ]* 8.9 编写属性测试：结果结构完整性
    - **属性 8：result structure completeness**
    - **验证需求：6.3, 7.1, 7.2, 7.3**

  - [ ]* 8.10 编写属性测试：无效输入验证
    - **属性 9：invalid input validation**
    - **验证需求：8.1, 8.2, 8.3, 8.4**

  - [ ]* 8.11 编写属性测试：跳结果顺序与路径任务顺序一致
    - **属性 10：hop result order matches path task order**
    - **验证需求：1.5, 7.1**

  - [ ]* 8.12 编写属性测试：低优先级阻塞上界
    - **属性 11：LP blocking upper bound**
    - **验证需求：2.3**

  - [ ]* 8.13 编写属性测试：初始 Smax/Smin 正确性
    - **属性 12：initial Smax/Smin correctness**
    - **验证需求：4.1**

  - [ ]* 8.14 编写单元测试
    - 使用论文数值案例验证分析结果正确性
    - 测试边界情况：单跳路径、单流网络、纯 FIFO、无低优先级流、技术延迟为 0、包含 ForwardingTask 的路径
    - 测试错误条件：各种无效输入配置（对应需求 8）
    - 测试 analyze_all 与 analyze_path 结果一致性
    - 测试 print_results 不抛出异常
    - _需求：8.1, 8.2, 8.3, 8.4, 6.1, 6.2, 6.4_

- [x] 9. 最终检查点 - 确保所有测试通过
  - 确保所有测试通过，如有疑问请询问用户。

## 说明

- 标记 `*` 的任务为可选任务，可跳过以加速 MVP 开发
- 每个任务引用了具体的需求编号以确保可追溯性
- 检查点任务确保增量验证
- 属性测试验证通用正确性属性，单元测试验证特定示例和边界情况
