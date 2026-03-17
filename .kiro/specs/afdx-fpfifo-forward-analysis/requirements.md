# 需求文档

## 简介

本功能将论文 "Forward end-to-end delay analysis extension for FP/FIFO policy in AFDX networks"（Benammar 等，2017）中提出的前向端到端延迟分析方法集成到 pycpa 项目中。该方法针对 AFDX 网络中固定优先级（FP）与 FIFO 策略的组合调度，通过逐跳前向传播 Smax/Smin（最大/最小累积服务曲线）来计算更紧凑的最坏情况端到端延迟上界。

实现作为独立模块放置在 `forward_analysis/` 文件夹下（与 `pycpa/` 同级），读取 pycpa 的模型对象（System、Resource、Task、Path、EventModel）作为输入，但运行自身独立的分析算法，不融入 pycpa 的 CPA 分析循环。

## 术语表

- **AFDX_Network**: 航空全双工交换以太网（Avionics Full-Duplex Switched Ethernet），一种用于航空电子系统的确定性以太网标准
- **Virtual_Link (VL)**: AFDX 网络中的虚拟链路，定义了从源端系统到一个或多个目的端系统的单向数据流路径，具有固定的 BAG（Bandwidth Allocation Gap）和最大帧长
- **BAG**: 带宽分配间隔（Bandwidth Allocation Gap），VL 的最小帧间隔，等价于 pycpa 中 PJdEventModel 的周期 P
- **Smax**: 在某一跳处，VL 帧的最大累积延迟（最坏情况到达时间偏移），用于前向分析中逐跳传播
- **Smin**: 在某一跳处，VL 帧的最小累积延迟（最好情况到达时间偏移），用于前向分析中逐跳传播
- **FP_Scheduler**: 固定优先级调度器，高优先级流量抢占低优先级流量的服务
- **FIFO_Policy**: 先进先出策略，同一优先级内的流量按到达顺序服务
- **FP_FIFO_Scheduler**: 固定优先级与 FIFO 组合调度策略，优先级间为 FP，同优先级内为 FIFO
- **Forward_Analyzer**: 前向分析器，实现论文中逐跳前向传播 Smax/Smin 的核心分析算法
- **Serialization_Effect**: 序列化效应，同一 VL 的多个帧在同一输出端口排队时产生的额外延迟
- **Technological_Latency**: 交换机的技术延迟（转发延迟），帧通过交换机内部处理所需的固定时间
- **Jitter**: 抖动，帧到达时间相对于理想周期的偏差范围
- **End_System**: AFDX 网络中的端系统（终端节点），产生或消费 VL 流量
- **Switch**: AFDX 网络中的交换机节点，转发 VL 帧并引入调度延迟
- **Flow_Path**: 一条 VL 从源端系统经过若干交换机到达目的端系统的完整路径
- **Hop_Result**: 单跳分析结果，包含该跳的 Smax、Smin、最坏情况响应时间等信息
- **Analysis_Result**: 完整的分析结果集合，包含所有 VL 在所有跳的 Hop_Result 以及端到端延迟

## 需求

### 需求 1：AFDX 网络模型构建

**用户故事：** 作为航空电子系统工程师，我希望使用 pycpa 已有的模型对象来描述 AFDX 网络拓扑和流量配置，以便复用已有的建模接口进行前向分析。

#### 验收标准

1. THE Forward_Analyzer SHALL 接受 pycpa 的 System 对象作为输入，从中读取 Resource（交换机端口）、Task（VL 在各跳的传输任务）、Path（VL 的端到端路径）和 EventModel（VL 的激活模型）信息
2. WHEN 用户使用 pycpa 的 Resource 对象表示 AFDX 交换机输出端口时，THE Forward_Analyzer SHALL 从 Resource 的 tasks 集合中识别该端口上的所有竞争流量
3. WHEN 用户使用 pycpa 的 Task 对象表示 VL 在某一跳的传输时，THE Forward_Analyzer SHALL 从 Task 的 wcet（最坏情况传输时间）、bcet（最好情况传输时间）和 scheduling_parameter（优先级）属性中读取分析所需参数
4. WHEN 用户使用 pycpa 的 PJdEventModel 设置 VL 的源端激活模型时，THE Forward_Analyzer SHALL 从 PJdEventModel 的 P（周期/BAG）和 J（初始抖动）属性中读取流量特征
5. WHEN 用户使用 pycpa 的 Path 对象定义 VL 的端到端路径时，THE Forward_Analyzer SHALL 按 Path.tasks 列表的顺序依次分析各跳

### 需求 2：FP/FIFO 前向单跳延迟分析

**用户故事：** 作为网络分析工程师，我希望系统能够计算 AFDX 交换机输出端口上 FP/FIFO 调度策略下单跳的最坏情况延迟，以便逐跳构建端到端延迟分析。

#### 验收标准

1. WHEN 分析某一跳时，THE Forward_Analyzer SHALL 根据论文公式计算高优先级流量对被分析 VL 的抢占干扰量
2. WHEN 分析某一跳时，THE Forward_Analyzer SHALL 根据论文公式计算同优先级流量对被分析 VL 的 FIFO 排队干扰量，利用各竞争流的 Smax 和 Smin 信息确定同时排队的帧数
3. WHEN 分析某一跳时，THE Forward_Analyzer SHALL 根据论文公式计算低优先级流量对被分析 VL 的非抢占阻塞量（最大低优先级帧传输时间）
4. WHEN 分析某一跳时，THE Forward_Analyzer SHALL 将高优先级干扰、同优先级 FIFO 干扰、低优先级阻塞和被分析帧自身传输时间求和，得到该跳的最坏情况响应时间上界
5. WHEN 分析某一跳时，THE Forward_Analyzer SHALL 计算并更新被分析 VL 在该跳输出处的 Smax 值（累积最大延迟）
6. WHEN 分析某一跳时，THE Forward_Analyzer SHALL 计算并更新被分析 VL 在该跳输出处的 Smin 值（累积最小延迟）

### 需求 3：序列化效应处理

**用户故事：** 作为网络分析工程师，我希望分析方法能够正确处理 AFDX 网络中的序列化效应，以便获得更精确的延迟上界。

#### 验收标准

1. WHEN 启用序列化分析模式时，THE Forward_Analyzer SHALL 在计算同优先级 FIFO 干扰时考虑来自同一输入端口的帧的序列化约束（同一输入链路上的帧不会同时到达）
2. WHEN 未启用序列化分析模式时，THE Forward_Analyzer SHALL 忽略序列化约束，将所有同优先级帧视为可能同时到达
3. THE Forward_Analyzer SHALL 提供 with_serialization 参数，允许用户选择是否启用序列化效应分析

### 需求 4：逐跳前向传播

**用户故事：** 作为网络分析工程师，我希望分析方法能够沿 VL 路径逐跳前向传播延迟信息，以便利用上游跳的分析结果收紧下游跳的延迟上界。

#### 验收标准

1. WHEN 分析 VL 路径的第一跳时，THE Forward_Analyzer SHALL 根据源端 EventModel 的参数（BAG 和初始抖动）初始化 Smax 和 Smin 的初始值
2. WHEN 分析 VL 路径的后续跳时，THE Forward_Analyzer SHALL 使用前一跳输出的 Smax 和 Smin 值作为当前跳的输入
3. WHEN 所有跳分析完成后，THE Forward_Analyzer SHALL 使用最后一跳的 Smax 值减去 Smin 初始值来计算端到端最坏情况延迟上界
4. THE Forward_Analyzer SHALL 支持在每一跳添加可配置的技术延迟（Technological_Latency），将其累加到 Smax 和 Smin 中

### 需求 5：交换机技术延迟配置

**用户故事：** 作为网络分析工程师，我希望能够为每个交换机配置不同的技术延迟（转发延迟），以便准确建模实际 AFDX 网络中不同交换机的处理延迟。

#### 验收标准

1. THE Forward_Analyzer SHALL 支持通过 Resource 对象的属性或分析参数为每个交换机端口配置技术延迟值
2. WHEN 未显式配置技术延迟时，THE Forward_Analyzer SHALL 使用默认值 0
3. WHEN Resource 对象具有 forwarding_delay 属性时，THE Forward_Analyzer SHALL 读取该属性作为该交换机端口的技术延迟

### 需求 6：完整分析接口

**用户故事：** 作为系统集成工程师，我希望通过简洁的接口调用来运行论文提出的前向分析方法，以便快速获取所有 VL 的端到端延迟结果。

#### 验收标准

1. THE Forward_Analyzer SHALL 提供 analyze_all 方法，一次性分析 System 中所有已注册 Path 上的所有 VL
2. THE Forward_Analyzer SHALL 提供 analyze_path 方法，分析单条 Path 上的 VL 端到端延迟
3. WHEN analyze_all 或 analyze_path 执行完成后，THE Forward_Analyzer SHALL 返回 Analysis_Result 对象，包含每条 VL 在每一跳的 Hop_Result（Smax、Smin、单跳最坏响应时间）以及端到端延迟上界
4. THE Forward_Analyzer SHALL 提供 print_results 方法，以可读格式打印分析结果，包括每条 VL 的逐跳延迟和端到端延迟

### 需求 7：分析结果数据结构

**用户故事：** 作为开发者，我希望分析结果以结构化的数据对象返回，以便程序化地访问和处理分析结果。

#### 验收标准

1. THE Hop_Result SHALL 包含以下字段：跳索引（hop_index）、对应的 Resource 名称、Smax 值、Smin 值、单跳最坏情况响应时间（wcrt）
2. THE Analysis_Result SHALL 包含以下字段：Path 引用、逐跳 Hop_Result 列表、端到端最坏情况延迟上界（e2e_wcrt）
3. THE Forward_Analyzer SHALL 将所有 Path 的 Analysis_Result 存储在一个字典中，以 Path 对象为键

### 需求 8：输入验证

**用户故事：** 作为用户，我希望在输入参数不合法时获得清晰的错误提示，以便快速定位和修正配置问题。

#### 验收标准

1. IF Path 中的 Task 未绑定到任何 Resource，THEN THE Forward_Analyzer SHALL 抛出 ValueError 异常并说明哪个 Task 缺少 Resource 绑定
2. IF Path 中第一个 Task 未设置 in_event_model，THEN THE Forward_Analyzer SHALL 抛出 ValueError 异常并说明哪个 VL 缺少源端事件模型
3. IF Task 的 wcet 小于或等于 0，THEN THE Forward_Analyzer SHALL 抛出 ValueError 异常并说明哪个 Task 的执行时间参数无效
4. IF Task 未设置 scheduling_parameter 属性，THEN THE Forward_Analyzer SHALL 抛出 ValueError 异常并说明哪个 Task 缺少优先级配置

### 需求 9：示例与验证

**用户故事：** 作为用户，我希望有一个完整的示例脚本来演示如何使用前向分析方法，并能与论文中的数值结果进行对比验证。

#### 验收标准

1. THE Example_Script SHALL 构建一个与论文中案例一致的 AFDX 网络拓扑（包含交换机、VL、优先级配置）
2. THE Example_Script SHALL 使用 pycpa 的 System、Resource、Task、Path、PJdEventModel 对象构建网络模型
3. THE Example_Script SHALL 调用 Forward_Analyzer 的 analyze_all 方法执行前向分析
4. THE Example_Script SHALL 打印每条 VL 的逐跳分析结果和端到端延迟
5. THE Example_Script SHALL 将分析结果与论文中的参考值进行对比，并输出对比结果
6. THE Example_Script SHALL 放置在 examples/afdx_forward_analysis/ 目录下

### 需求 10：模块独立性

**用户故事：** 作为开发者，我希望前向分析模块与 pycpa 的 CPA 分析架构保持独立，以便独立维护和扩展。

#### 验收标准

1. THE Forward_Analyzer SHALL 仅依赖 pycpa 的模型层（model 模块）读取网络配置，不依赖 pycpa 的 analysis、schedulers 或 path_analysis 模块
2. THE Forward_Analyzer SHALL 实现在 forward_analysis/ 文件夹下，与 pycpa/ 文件夹同级
3. THE Forward_Analyzer SHALL 将核心分析逻辑实现在 forward_analysis/fa_fpfifo.py 文件中
4. THE Forward_Analyzer SHALL 通过 forward_analysis 包的 __init__.py 导出 FPFIFOForwardAnalyzer 类，使用户可通过 `from forward_analysis import FPFIFOForwardAnalyzer` 导入
