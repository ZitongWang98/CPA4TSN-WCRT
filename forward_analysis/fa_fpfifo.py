"""
FP/FIFO Forward End-to-End Delay Analysis for AFDX Networks.

Implements the forward analysis method from:
  Benammar N, Ridouard F, Bauer H, et al.
  "Forward end-to-end delay analysis extension for FP/FIFO policy
   in AFDX networks"[C]//2017 22nd IEEE International Conference on
  Emerging Technologies and Factory Automation (ETFA). IEEE, 2017: 1-8.

Core analysis logic: backlog-based forward propagation of Smax/Smin
under Fixed-Priority / FIFO combined scheduling.

Theorem 2: FA-FP/FIFO without serialization effect  (Formula 9)
Theorem 4: FA-FP/FIFO with serialization effect     (Formula 12)
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set

from pycpa import model


@dataclass
class HopResult:
    """单跳分析结果。"""
    hop_index: int          # 跳索引（从 0 开始）
    resource_name: str      # 对应 Resource 的名称
    task_name: str          # 对应 Task 的名称
    smax: float             # 该跳输出处的 Smax（最大累积延迟）
    smin: float             # 该跳输出处的 Smin（最小累积延迟）
    wcrt: float             # 该跳的 backlog（最大积压量）


@dataclass
class AnalysisResult:
    """单条 Path 的完整分析结果。"""
    path: model.Path                # 对应的 Path 对象
    path_name: str                  # Path 名称
    hop_results: List[HopResult]    # 逐跳结果列表
    e2e_wcrt: float                 # 端到端最坏情况延迟上界
    smax_initial: float             # 初始 Smax 值
    smin_initial: float             # 初始 Smin 值


class FPFIFOForwardAnalyzer:
    """AFDX FP/FIFO 前向端到端延迟分析器。"""

    def __init__(self, system: model.System):
        self.system = system
        self._smax_map: Dict[model.Task, float] = {}
        self._smin_map: Dict[model.Task, float] = {}
        self._bklg_map: Dict[model.Task, float] = {}
        self._last_results: Dict[model.Path, AnalysisResult] = None

    def _validate_path(self, path: model.Path) -> None:
        """验证 Path 的所有 Task 是否满足分析前提条件。"""
        for task in path.tasks:
            if task.resource is None:
                raise ValueError(
                    f"Task '{task.name}' is not bound to any Resource"
                )

        analysis_tasks = [
            t for t in path.tasks if not isinstance(t, model.ForwardingTask)
        ]

        if not analysis_tasks:
            raise ValueError(
                f"Path '{path.name}' has no analyzable tasks (after filtering ForwardingTasks)"
            )

        first_task = analysis_tasks[0]
        if first_task.in_event_model is None:
            raise ValueError(
                f"First task '{first_task.name}' in path '{path.name}' has no in_event_model"
            )

        for task in analysis_tasks:
            if task.wcet <= 0:
                raise ValueError(
                    f"Task '{task.name}' has invalid wcet={task.wcet} (must be > 0)"
                )
            if not hasattr(task, 'scheduling_parameter'):
                raise ValueError(
                    f"Task '{task.name}' has no scheduling_parameter"
                )

    def _get_analysis_tasks(self, path: model.Path) -> List[model.Task]:
        """从 Path.tasks 中过滤掉 ForwardingTask，返回参与 FP/FIFO 调度的任务列表。"""
        return [t for t in path.tasks if not isinstance(t, model.ForwardingTask)]

    def _get_technological_latency(self, resource: model.Resource) -> float:
        """获取交换机端口的技术延迟（转发延迟）。"""
        return getattr(resource, 'forwarding_delay', 0)

    def _init_smax_smin(self, task: model.Task) -> Tuple[float, float]:
        """根据源端 EventModel 初始化第一跳的 Smax_0 和 Smin_0。

        返回 (Smax_0, Smin_0) = (J, 0)。
        """
        em = task.in_event_model
        smax_0 = em.J
        smin_0 = 0.0
        return smax_0, smin_0

    # ------------------------------------------------------------------
    # Core algorithm helpers (Paper Theorems 2 & 4)
    # ------------------------------------------------------------------

    def _rbf(self, task: model.Task, t: float, jitter: float) -> float:
        """Request bound function (Benammar et al., 2017, Section III-B).

        rbf(t, J) = (1 + floor((t + J) / T)) * C
        """
        if task.in_event_model is None:
            return 0.0
        if t + jitter < 0:
            return 0.0
        return (1 + math.floor((t + jitter) / task.in_event_model.P)) * task.wcet

    def _alpha_j(self, jitter: float, period: float) -> float:
        """Compute alpha_j (Benammar et al., 2017, Formula 11).

        alpha_j = (k+1)*T - J where k = floor(J/T).
        Used in Theorem 4 serialization terms.
        """
        if period <= 0:
            return 0.0
        k = math.floor(jitter / period)
        return (k + 1) * period - jitter

    def _classify_tasks(self, task: model.Task, resource: model.Resource):
        """Classify non-ForwardingTask tasks on a resource into hp, sp, lp.

        sp includes task_i itself (paper definition).
        Returns (hp, sp, lp) lists.
        """
        hp, sp, lp = [], [], []
        for t in resource.tasks:
            if isinstance(t, model.ForwardingTask):
                continue
            if t.in_event_model is None:
                continue
            if t.scheduling_parameter < task.scheduling_parameter:
                hp.append(t)
            elif t.scheduling_parameter == task.scheduling_parameter:
                sp.append(t)  # includes task itself
            else:
                lp.append(t)
        return hp, sp, lp

    def _get_input_resources(self, resource: model.Resource) -> Set:
        """Get the set of predecessor Resources (input links) for a resource.

        Detected via prev_task.resource for all tasks on this resource.
        """
        preds = set()
        for t in resource.tasks:
            if isinstance(t, model.ForwardingTask):
                continue
            if hasattr(t, 'prev_task') and t.prev_task is not None:
                prev_res = getattr(t.prev_task, 'resource', None)
                if prev_res is not None:
                    preds.add(prev_res)
        return preds

    def _tasks_via_input(self, resource: model.Resource, pred_resource: model.Resource) -> List[model.Task]:
        """Get tasks on resource that arrive via pred_resource."""
        result = []
        for t in resource.tasks:
            if isinstance(t, model.ForwardingTask):
                continue
            if t.in_event_model is None:
                continue
            if hasattr(t, 'prev_task') and t.prev_task is not None:
                if getattr(t.prev_task, 'resource', None) is pred_resource:
                    result.append(t)
        return result

    def _is_source_task(self, task: model.Task) -> bool:
        """Check if task is at a source node (no predecessor task)."""
        return not (hasattr(task, 'prev_task') and task.prev_task is not None)

    def _candidate_times(self, resource: model.Resource, jitters: Dict[model.Task, float],
                         t_cap: float = 200000.0) -> List[float]:
        """Generate candidate times for backlog search.

        Candidates: 0, k*T, alpha+k*T, J+k*T for all flows at the resource.
        """
        times = {0.0}
        for t in resource.tasks:
            if isinstance(t, model.ForwardingTask):
                continue
            if t.in_event_model is None:
                continue
            J = jitters.get(t, 0.0)
            T = t.in_event_model.P
            if T <= 0:
                continue
            alpha = self._alpha_j(J, T)
            for k in range(30):
                t1 = k * T
                t2 = alpha + k * T
                t3 = max(0.0, J) + k * T
                if t1 <= t_cap:
                    times.add(t1)
                if 0 <= t2 <= t_cap:
                    times.add(t2)
                if t3 <= t_cap:
                    times.add(t3)
        return sorted(t for t in times if 0 <= t <= t_cap)

    # ------------------------------------------------------------------
    # Workload functions
    # Benammar N, Ridouard F, Bauer H, et al., ETFA 2017, Theorems 2 & 4
    # ------------------------------------------------------------------

    def _W_theorem2(self, task_i: model.Task, resource: model.Resource,
                    t: float, jitters: Dict[model.Task, float],
                    hp: List, sp: List, lp: List) -> float:
        """Workload function WITHOUT serialization (Theorem 2, Formula 9).

        W(k+1) = max_lp(Cj) + Σ_{sp} rbf_j(t, J_j) + Σ_{hp} rbf_j(W(k)-Ci, J_j)

        sp includes vi itself. HP uses fixed-point on W.
        """
        Ci = task_i.wcet
        lp_block = max((t.wcet for t in lp), default=0.0)
        sp_work = sum(self._rbf(f, t, jitters.get(f, 0.0)) for f in sp)

        W = Ci  # initial value for fixed-point
        for _ in range(200):
            hp_work = sum(self._rbf(f, max(0, W - Ci), jitters.get(f, 0.0)) for f in hp)
            W_new = lp_block + sp_work + hp_work
            if abs(W_new - W) < 1e-6:
                return W_new
            W = W_new
        return W

    def _W_serialized(self, task_i: model.Task, resource: model.Resource,
                      t: float, jitters: Dict[model.Task, float],
                      hp: List, sp: List, lp: List) -> float:
        """Workload function WITH serialization (Theorem 4, Formula 12).

        W(k+1) = max_lp(Cj) + Σ_{hp} rbf_j(W(k)-Ci, J_j)
                 + Σ_x [min(A_x + B_x, t + max_{shp_x}(Cj)) - B_x]

        Falls back to Theorem 2 if no predecessor links (source nodes).
        """
        preds = self._get_input_resources(resource)
        if not preds:
            return self._W_theorem2(task_i, resource, t, jitters, hp, sp, lp)

        Ci = task_i.wcet
        lp_block = max((tk.wcet for tk in lp), default=0.0)

        W = Ci
        for _ in range(200):
            hp_total = sum(self._rbf(f, max(0, W - Ci), jitters.get(f, 0.0)) for f in hp)

            link_sum = 0.0
            for pred_res in preds:
                flows_x = self._tasks_via_input(resource, pred_res)
                sp_x = [f for f in flows_x if f.scheduling_parameter == task_i.scheduling_parameter]
                hp_x = [f for f in flows_x if f.scheduling_parameter < task_i.scheduling_parameter]
                shp_x = sp_x + hp_x

                if not shp_x:
                    continue

                A_x = sum(self._rbf(f, t, jitters.get(f, 0.0)) for f in sp_x)
                B_x = 0.0
                for f in hp_x:
                    alpha = self._alpha_j(jitters.get(f, 0.0), f.in_event_model.P)
                    if t >= alpha:
                        B_x += math.floor((t - alpha) / f.in_event_model.P) * f.wcet

                max_C_shp = max((f.wcet for f in shp_x), default=0.0)
                cap = t + max_C_shp
                link_sum += min(A_x + B_x, cap) - B_x

            W_new = lp_block + hp_total + link_sum
            if abs(W_new - W) < 1e-6:
                return W_new
            W = W_new
        return W

    # ------------------------------------------------------------------
    # Backlog computation
    # ------------------------------------------------------------------

    def _compute_bklg(self, task: model.Task, resource: model.Resource,
                      with_serialization: bool) -> float:
        """Compute max backlog Bklg = max_t(W(t) - t) (Benammar et al., 2017, Section III-C).

        Searches over candidate times t to find the maximum backlog.

        :param task: the task being analyzed
        :param resource: the resource (queue) the task is on
        :param with_serialization: whether to use Theorem 4
        :return: maximum backlog value
        """
        is_source = self._is_source_task(task)

        # Compute jitters for all tasks on this resource
        jitters: Dict[model.Task, float] = {}
        for t in resource.tasks:
            if isinstance(t, model.ForwardingTask):
                continue
            sm = self._smax_map.get(t, 0.0)
            sn = self._smin_map.get(t, 0.0)
            jitters[t] = max(0.0, sm - sn)

        hp, sp, lp = self._classify_tasks(task, resource)
        t_candidates = self._candidate_times(resource, jitters)

        max_bklg = 0.0
        for tc in t_candidates:
            if tc < 0:
                continue
            if with_serialization and not is_source:
                W = self._W_serialized(task, resource, tc, jitters, hp, sp, lp)
            else:
                W = self._W_theorem2(task, resource, tc, jitters, hp, sp, lp)
            b = W - tc
            if b > max_bklg:
                max_bklg = b
            if W <= tc and tc > 0:
                break
        return max_bklg

    # ------------------------------------------------------------------
    # Resource ordering for multi-pass propagation
    # ------------------------------------------------------------------

    def _resource_order(self) -> List[model.Resource]:
        """Determine processing order for resources.

        Source resources (ES->S edges) first, then switch resources.
        """
        source_res = set()
        non_source_res = set()
        for p in self.system.paths:
            tasks = self._get_analysis_tasks(p)
            for i, t in enumerate(tasks):
                if i == 0:
                    source_res.add(t.resource)
                else:
                    non_source_res.add(t.resource)
        # Remove any that appear in both (prefer source)
        non_source_res -= source_res
        return sorted(source_res, key=lambda r: r.name) + sorted(non_source_res, key=lambda r: r.name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_path(self, path: model.Path, with_serialization: bool = False) -> AnalysisResult:
        """分析单条 Path 的端到端延迟。"""
        self._validate_path(path)
        analysis_tasks = self._get_analysis_tasks(path)

        # Initialize Smax/Smin for ALL tasks in ALL paths
        for p in self.system.paths:
            tasks_p = self._get_analysis_tasks(p)
            if tasks_p and tasks_p[0].in_event_model is not None:
                smax_0, smin_0 = self._init_smax_smin(tasks_p[0])
                for t in tasks_p:
                    self._smax_map[t] = smax_0
                    self._smin_map[t] = smin_0

        smax_initial = self._smax_map[analysis_tasks[0]]
        smin_initial = self._smin_map[analysis_tasks[0]]

        # Multi-pass propagation for the target path
        for _ in range(20):
            changed = False
            for i, task in enumerate(analysis_tasks):
                resource = task.resource
                bklg = self._compute_bklg(task, resource, with_serialization)
                old_b = self._bklg_map.get(task)
                if old_b is None or abs(old_b - bklg) > 1e-6:
                    changed = True
                self._bklg_map[task] = bklg

                tech_lat = self._get_technological_latency(resource)
                new_smax = self._smax_map[task] + bklg + tech_lat
                new_smin = self._smin_map[task] + task.wcet + tech_lat

                # Propagate to next hop if exists
                if i + 1 < len(analysis_tasks):
                    next_task = analysis_tasks[i + 1]
                    if abs(self._smax_map.get(next_task, 0.0) - new_smax) > 1e-6:
                        changed = True
                    self._smax_map[next_task] = new_smax
                    self._smin_map[next_task] = new_smin

            if not changed:
                break

        # Build hop results
        hop_results = []
        for i, task in enumerate(analysis_tasks):
            bklg = self._bklg_map.get(task, 0.0)
            tech_lat = self._get_technological_latency(task.resource)
            smax_out = self._smax_map[task] + bklg + tech_lat
            smin_out = self._smin_map[task] + task.wcet + tech_lat
            hop_results.append(HopResult(
                hop_index=i,
                resource_name=task.resource.name,
                task_name=task.name,
                smax=smax_out,
                smin=smin_out,
                wcrt=bklg,
            ))

        # E2E delay = smax_input[last] + bklg[last]
        # (no tech_lat — that's only added when propagating to next hop)
        last_task = analysis_tasks[-1]
        last_bklg = self._bklg_map.get(last_task, 0.0)
        e2e_wcrt = self._smax_map[last_task] + last_bklg

        return AnalysisResult(
            path=path,
            path_name=path.name,
            hop_results=hop_results,
            e2e_wcrt=e2e_wcrt,
            smax_initial=smax_initial,
            smin_initial=smin_initial,
        )

    def analyze_all(self, with_serialization: bool = False) -> Dict[model.Path, AnalysisResult]:
        """分析系统中所有已注册 Path 的端到端延迟。"""
        if not self.system.paths:
            self._last_results = {}
            return {}

        # Reset internal state
        self._smax_map.clear()
        self._smin_map.clear()
        self._bklg_map.clear()

        # Validate all paths
        for p in self.system.paths:
            self._validate_path(p)

        # Build task-to-path mapping and path task lists
        path_tasks: Dict[model.Path, List[model.Task]] = {}
        for p in self.system.paths:
            path_tasks[p] = self._get_analysis_tasks(p)

        # Initialize Smax/Smin for ALL first-hop tasks
        for p in self.system.paths:
            tasks_p = path_tasks[p]
            if tasks_p and tasks_p[0].in_event_model is not None:
                smax_0, smin_0 = self._init_smax_smin(tasks_p[0])
                for t in tasks_p:
                    self._smax_map[t] = smax_0
                    self._smin_map[t] = smin_0

        # Get resource processing order
        res_order = self._resource_order()

        # Multi-pass propagation (iterate until convergence)
        for _ in range(20):
            changed = False
            for resource in res_order:
                # Compute bklg for each non-ForwardingTask on this resource
                for task in resource.tasks:
                    if isinstance(task, model.ForwardingTask):
                        continue
                    if task not in self._smin_map:
                        continue
                    bklg = self._compute_bklg(task, resource, with_serialization)
                    old_b = self._bklg_map.get(task)
                    if old_b is None or abs(old_b - bklg) > 1e-6:
                        changed = True
                    self._bklg_map[task] = bklg

                # Propagate Smax/Smin to next hops for ALL paths
                for p in self.system.paths:
                    tasks_p = path_tasks[p]
                    for i, task in enumerate(tasks_p):
                        if task.resource is not resource:
                            continue
                        if task not in self._bklg_map:
                            continue
                        bklg = self._bklg_map[task]
                        tech_lat = self._get_technological_latency(resource)
                        new_smax = self._smax_map[task] + bklg + tech_lat
                        new_smin = self._smin_map[task] + task.wcet + tech_lat

                        if i + 1 < len(tasks_p):
                            next_task = tasks_p[i + 1]
                            if abs(self._smax_map.get(next_task, 0.0) - new_smax) > 1e-6:
                                changed = True
                            self._smax_map[next_task] = new_smax
                            self._smin_map[next_task] = new_smin

            if not changed:
                break

        # Build results for each path
        results = {}
        for p in self.system.paths:
            tasks_p = path_tasks[p]
            smax_initial = self._smax_map[tasks_p[0]]
            smin_initial = self._smin_map[tasks_p[0]]

            hop_results = []
            for i, task in enumerate(tasks_p):
                bklg = self._bklg_map.get(task, 0.0)
                tech_lat = self._get_technological_latency(task.resource)
                smax_out = self._smax_map[task] + bklg + tech_lat
                smin_out = self._smin_map[task] + task.wcet + tech_lat
                hop_results.append(HopResult(
                    hop_index=i,
                    resource_name=task.resource.name,
                    task_name=task.name,
                    smax=smax_out,
                    smin=smin_out,
                    wcrt=bklg,
                ))

            last_task = tasks_p[-1]
            last_bklg = self._bklg_map.get(last_task, 0.0)
            e2e_wcrt = self._smax_map[last_task] + last_bklg

            results[p] = AnalysisResult(
                path=p,
                path_name=p.name,
                hop_results=hop_results,
                e2e_wcrt=e2e_wcrt,
                smax_initial=smax_initial,
                smin_initial=smin_initial,
            )

        self._last_results = results
        return results

    def print_results(self, results: Dict[model.Path, AnalysisResult] = None) -> None:
        """以可读格式打印分析结果。"""
        if results is None:
            results = self._last_results
        if results is None:
            print("No analysis results available. Run analyze_all() first.")
            return

        print("=" * 72)
        print("AFDX FP/FIFO Forward Analysis Results")
        print("=" * 72)

        for path, result in results.items():
            print(f"\nPath: {result.path_name}    e2e_wcrt = {result.e2e_wcrt:.4f}")
            print("-" * 72)
            print(f"  {'Hop':>3}  {'Resource':<20} {'Task':<20} {'wcrt':>10} {'Smax':>10} {'Smin':>10}")
            print(f"  {'---':>3}  {'--------':<20} {'----':<20} {'----':>10} {'----':>10} {'----':>10}")
            for hop in result.hop_results:
                print(
                    f"  {hop.hop_index:>3}  {hop.resource_name:<20} {hop.task_name:<20} "
                    f"{hop.wcrt:>10.4f} {hop.smax:>10.4f} {hop.smin:>10.4f}"
                )
            print()
