"""
Internal DNS Server

仅解析 *.vpn.example.com 域名，将设备名映射到 VPN IP。
"""

import socket
import threading
from typing import Optional

from dnslib import DNSRecord, DNSHeader, RR, A, QTYPE

from .core.wg_parser import WgParser
from .config import settings


class InternalDNSServer:
    """内部 DNS 服务器"""
    
    def __init__(
        self,
        listen_address: str = "10.8.0.1",
        listen_port: int = 53,
        domain_suffix: str = ".vpn.example.com",
        wg_config_path: str = "/etc/wireguard/wg0.conf",
    ):
        self.listen_address = listen_address
        self.listen_port = listen_port
        self.domain_suffix = domain_suffix.lower()
        self.wg_parser = WgParser(wg_config_path)
        self.socket: Optional[socket.socket] = None
        self.running = False
        self._thread: Optional[threading.Thread] = None
    
    def get_name_to_ip_mapping(self) -> dict[str, str]:
        """从 WireGuard 配置构建 name -> IP 映射"""
        mapping = {}
        
        try:
            peers = self.wg_parser.parse_peers()
            for peer in peers:
                # 将设备名转换为小写用于 DNS 查询
                name = peer.name.lower()
                # 从 AllowedIPs 提取 IP (格式: 10.8.0.x/32)
                ip = peer.allowed_ips.split("/")[0]
                mapping[name] = ip
        except FileNotFoundError:
            pass
        
        # 添加服务器自身
        mapping["server"] = "10.8.0.1"
        mapping["gateway"] = "10.8.0.1"
        
        return mapping
    
    def resolve_query(self, qname: str, qtype: int) -> Optional[str]:
        """
        解析 DNS 查询
        
        返回 IP 地址或 None (NXDOMAIN)
        """
        qname = qname.lower().rstrip(".")
        
        # 只处理 A 记录查询
        if qtype != QTYPE.A:
            return None
        
        # 检查域名后缀
        if not qname.endswith(self.domain_suffix):
            return None
        
        # 提取设备名 (去除域名后缀)
        device_name = qname[:-len(self.domain_suffix)]
        
        # 查找映射
        mapping = self.get_name_to_ip_mapping()
        return mapping.get(device_name)
    
    def handle_request(self, data: bytes, addr: tuple) -> bytes:
        """处理单个 DNS 请求"""
        try:
            request = DNSRecord.parse(data)
        except Exception:
            return b""
        
        # 获取查询信息
        qname = str(request.q.qname)
        qtype = request.q.qtype
        
        # 尝试解析
        ip = self.resolve_query(qname, qtype)
        
        # 构建响应
        if ip:
            # 找到记录
            reply = request.reply()
            reply.add_answer(RR(
                rname=request.q.qname,
                rtype=QTYPE.A,
                rclass=1,
                ttl=60,
                rdata=A(ip),
            ))
        else:
            # NXDOMAIN
            reply = request.reply()
            reply.header.rcode = 3  # NXDOMAIN
        
        return reply.pack()
    
    def serve_forever(self):
        """启动 DNS 服务 (阻塞)"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.listen_address, self.listen_port))
        self.socket.settimeout(1.0)
        
        self.running = True
        print(f"DNS Server listening on {self.listen_address}:{self.listen_port}")
        
        while self.running:
            try:
                data, addr = self.socket.recvfrom(512)
                response = self.handle_request(data, addr)
                if response:
                    self.socket.sendto(response, addr)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"DNS Error: {e}")
        
        self.socket.close()
    
    def start_background(self):
        """在后台线程启动 DNS 服务"""
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
    
    def stop(self):
        """停止 DNS 服务"""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)


def create_dns_server() -> InternalDNSServer:
    """创建 DNS 服务器实例"""
    return InternalDNSServer(
        listen_address=settings.dns_listen_address,
        listen_port=settings.dns_listen_port,
        domain_suffix=settings.dns_domain_suffix,
        wg_config_path=settings.wg_config_path,
    )


if __name__ == "__main__":
    # 独立运行 DNS 服务器
    server = create_dns_server()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.stop()
