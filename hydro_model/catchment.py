import numpy as np
from .routing import BaseRoutingModule

class Node:
    """
    代表河网中的一个节点（如连接点、源头或出口）。
    """
    def __init__(self, node_id):
        self.id = node_id
        self.inflows = {}  # 存储来自上游河段的流量 {reach_id: flow}
        self.outflow = 0.0

    def calculate_outflow(self):
        """计算该节点的总出流量。"""
        self.outflow = sum(self.inflows.values())
        return self.outflow

class Reach:
    """
    代表两个节点之间的一段河道。
    """
    def __init__(self, reach_id, upstream_node_id, downstream_node_id, routing_module: BaseRoutingModule):
        self.id = reach_id
        self.upstream_node_id = upstream_node_id
        self.downstream_node_id = downstream_node_id
        self.routing_module = routing_module
        self.lateral_inflow = 0.0 # 当前时间步的侧向入流

    def route_flow(self, inflow):
        """
        执行一步汇流演算。
        :param inflow: 来自上游节点的总入流量。
        :return: 演算后的出流量。
        """
        total_inflow = inflow + self.lateral_inflow
        return self.routing_module.run(total_inflow)

class Catchment:
    """
    管理整个河网的拓扑结构和模拟过程。
    """
    def __init__(self):
        self.nodes = {}
        self.reaches = {}
        self.headwater_nodes = []
        self.simulation_order = [] # 存储排序后的河段ID

    def add_node(self, node_id):
        self.nodes[node_id] = Node(node_id)

    def add_reach(self, reach_id, upstream_node_id, downstream_node_id, routing_module):
        self.reaches[reach_id] = Reach(reach_id, upstream_node_id, downstream_node_id, routing_module)

    def _determine_simulation_order(self):
        """
        通过拓扑排序确定河段的计算顺序。
        这是一个简化的实现，假设ID可以代表顺序。
        对于更复杂的网络，需要一个真正的拓扑排序算法。
        """
        # 假设上游河段的ID总是比下游的小
        self.simulation_order = sorted(self.reaches.keys())

        # 找到所有没有上游河段汇入的节点作为源头
        downstream_ids = {r.downstream_node_id for r in self.reaches.values()}
        self.headwater_nodes = [nid for nid in self.nodes if nid not in downstream_ids]

    def run_simulation(self, headwater_inflows, lateral_inflows, num_steps):
        """
        运行整个河网的模拟。
        :param headwater_inflows: a dict of {node_id: [flow_t1, flow_t2, ...]}
        :param lateral_inflows: a dict of {reach_id: [flow_t1, flow_t2, ...]}
        :param num_steps: 总模拟步数。
        """
        self._determine_simulation_order()

        # 初始化结果存储
        reach_outflows = {rid: np.zeros(num_steps) for rid in self.reaches}
        node_outflows = {nid: np.zeros(num_steps) for nid in self.nodes}

        for t in range(num_steps):
            # 1. 设置源头节点和侧向入流
            for node_id in self.headwater_nodes:
                if node_id in headwater_inflows:
                    self.nodes[node_id].outflow = headwater_inflows[node_id][t]

            for reach_id, reach in self.reaches.items():
                if reach_id in lateral_inflows:
                    reach.lateral_inflow = lateral_inflows[reach_id][t]

            # 2. 按拓扑顺序计算每个河段
            for reach_id in self.simulation_order:
                reach = self.reaches[reach_id]

                # 从上游节点获取入流
                inflow_from_upstream_node = self.nodes[reach.upstream_node_id].outflow

                # 演算河段
                outflow = reach.route_flow(inflow_from_upstream_node)

                # 存储河段出流并更新下游节点的入流
                reach_outflows[reach_id][t] = outflow
                self.nodes[reach.downstream_node_id].inflows[reach_id] = outflow

            # 3. 计算所有非源头节点的总出流
            for node_id in self.nodes:
                if node_id not in self.headwater_nodes:
                    node_outflows[node_id][t] = self.nodes[node_id].calculate_outflow()

        return reach_outflows, node_outflows

    def run_iterative_simulation(self, headwater_inflows, lateral_inflows, num_steps, max_iter=20, convergence_threshold=0.01):
        """
        运行整个河网的模拟，支持环状网络。
        使用迭代方法在每个时间步内求解流量，直到收敛。
        """
        self._determine_simulation_order()

        reach_outflows = {rid: np.zeros(num_steps) for rid in self.reaches}
        node_outflows = {nid: np.zeros(num_steps) for nid in self.nodes}

        for t in range(num_steps):
            # 存储t-1时间步的模块状态
            module_states_prev_t = {rid: (r.routing_module.I_prev, r.routing_module.O_prev) for rid, r in self.reaches.items()}

            # 设置当前时间步的源头和侧向入流
            for node_id in self.headwater_nodes:
                if node_id in headwater_inflows:
                    self.nodes[node_id].outflow = headwater_inflows[node_id][t]

            for reach_id, reach in self.reaches.items():
                if reach_id in lateral_inflows:
                    reach.lateral_inflow = lateral_inflows[reach_id][t]

            # --- 开始迭代求解当前时间步 t ---
            for i in range(max_iter):
                node_outflows_prev_iter = {nid: n.outflow for nid, n in self.nodes.items()}

                # 在每次迭代开始时，重置模块状态到 t-1 的状态
                for reach_id, reach in self.reaches.items():
                    reach.routing_module.I_prev, reach.routing_module.O_prev = module_states_prev_t[reach_id]

                # 按拓扑顺序演算所有河段
                for reach_id in self.simulation_order:
                    reach = self.reaches[reach_id]
                    inflow = self.nodes[reach.upstream_node_id].outflow
                    outflow = reach.route_flow(inflow)
                    self.nodes[reach.downstream_node_id].inflows[reach_id] = outflow

                # 更新所有节点的出流量
                for node_id, node in self.nodes.items():
                    node.calculate_outflow()

                # 检查收敛性
                total_change = sum(abs(node.outflow - node_outflows_prev_iter[nid]) for nid, node in self.nodes.items())
                if total_change < convergence_threshold:
                    break

            if i == max_iter - 1:
                print(f"Warning: Timestep {t} did not converge after {max_iter} iterations.")

            # 存储当前时间步的最终结果
            for rid, r in self.reaches.items():
                reach_outflows[rid][t] = r.routing_module.O_prev
            for nid, n in self.nodes.items():
                node_outflows[nid][t] = n.outflow

        return reach_outflows, node_outflows
