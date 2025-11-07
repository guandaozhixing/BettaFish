"""
专为 AI Agent 设计的科研情报搜索工具集 (Tavily)

版本: 2.0
最后更新: 2025-08-24

此脚本将 Tavily 的通用网页搜索能力抽象为一套面向科研情报场景的专业工具。
代理只需根据任务意图选择合适的工具即可完成科研动态追踪、课题进展梳理、
团队成员画像等信息搜集，无需理解繁琐的参数组合。默认使用广域检索
（topic='general'），以覆盖 Google Scholar、arXiv、学术机构官网、科研媒体等来源。

新特性:
- 新增面向学术场景的术语、日志和提示描述，更贴合科研进展追踪需求。
- 输出结构继续保留 `published_date` 字段，用于记录论文/资讯发布日期。

主要工具:
- basic_scholarly_scan: 执行标准、快速的科研动态检索。
- deep_research_review: 对某个课题进行全面、系统的深度检索。
- search_latest_preprints: 捕捉24小时内的预印本与快讯更新。
- search_recent_publications: 回顾过去一周的新发表成果。
- search_visual_resources: 搜索图表、海报等可视化材料。
- search_publications_by_date: 在指定历史区间内回溯研究成果。
"""

import os
import sys
from typing import List, Dict, Any, Optional

# 添加utils目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
utils_dir = os.path.join(root_dir, 'utils')
if utils_dir not in sys.path:
    sys.path.append(utils_dir)

from retry_helper import with_graceful_retry, SEARCH_API_RETRY_CONFIG
from dataclasses import dataclass, field

# 运行前请确保已安装Tavily库: pip install tavily-python
try:
    from tavily import TavilyClient
except ImportError:
    raise ImportError("Tavily库未安装，请运行 `pip install tavily-python` 进行安装。")

# --- 1. 数据结构定义 ---

@dataclass
class SearchResult:
    """
    网页搜索结果数据类
    包含 published_date 属性来存储论文/资讯的发布日期
    """
    title: str
    url: str
    content: str
    score: Optional[float] = None
    raw_content: Optional[str] = None
    published_date: Optional[str] = None

@dataclass
class ImageResult:
    """图片搜索结果数据类"""
    url: str
    description: Optional[str] = None

@dataclass
class TavilyResponse:
    """封装Tavily API的完整返回结果，以便在工具间传递"""
    query: str
    answer: Optional[str] = None
    results: List[SearchResult] = field(default_factory=list)
    images: List[ImageResult] = field(default_factory=list)
    response_time: Optional[float] = None


# --- 2. 核心客户端与专用工具集 ---

class TavilyAcademicAgency:
    """
    一个包含多种科研情报检索工具的客户端。
    每个公共方法都设计为供 AI Agent 独立调用的工具。
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化客户端。
        Args:
            api_key: Tavily API密钥，若不提供则从环境变量 TAVILY_API_KEY 读取。
        """
        if api_key is None:
            api_key = os.getenv("TAVILY_API_KEY")
            if not api_key:
                raise ValueError("Tavily API Key未找到！请设置TAVILY_API_KEY环境变量或在初始化时提供")
        self._client = TavilyClient(api_key=api_key)

    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=TavilyResponse(query="搜索失败"))
    def _search_internal(self, **kwargs) -> TavilyResponse:
        """内部通用的搜索执行器，所有工具最终都调用此方法"""
        try:
            kwargs['topic'] = 'general'
            api_params = {k: v for k, v in kwargs.items() if v is not None}
            response_dict = self._client.search(**api_params)
            
            search_results = [
                SearchResult(
                    title=item.get('title'),
                    url=item.get('url'),
                    content=item.get('content'),
                    score=item.get('score'),
                    raw_content=item.get('raw_content'),
                    published_date=item.get('published_date')
                ) for item in response_dict.get('results', [])
            ]
            
            image_results = [ImageResult(url=item.get('url'), description=item.get('description')) for item in response_dict.get('images', [])]

            return TavilyResponse(
                query=response_dict.get('query'), answer=response_dict.get('answer'),
                results=search_results, images=image_results,
                response_time=response_dict.get('response_time')
            )
        except Exception as e:
            print(f"搜索时发生错误: {str(e)}")
            raise e  # 让重试机制捕获并处理

    # --- Agent 可用的工具方法 ---

    def basic_scholarly_scan(self, query: str, max_results: int = 7) -> TavilyResponse:
        """
        【工具】基础科研检索: 面向学术场景的通用快速搜索。
        适用于初步了解课题全貌、捕捉代表性论文、机构动态和资讯报道。
        Agent 可提供查询语句(query)和可选的最大结果数(max_results)。
        """
        print(f"--- TOOL: 基础科研检索 (query: {query}) ---")
        return self._search_internal(
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_answer=False
        )

    def deep_research_review(self, query: str) -> TavilyResponse:
        """
        【工具】深度科研综述: 对某个课题进行系统化的长链检索。
        返回 Tavily 的高级摘要与最多20条高度相关的学术/机构结果，
        适用于梳理研究脉络、核心论文、重点团队与竞品项目。
        """
        print(f"--- TOOL: 深度科研综述 (query: {query}) ---")
        return self._search_internal(
            query=query, search_depth="advanced", max_results=20, include_answer="advanced"
        )

    def search_latest_preprints(self, query: str) -> TavilyResponse:
        """
        【工具】追踪最新预印本: 获取24小时内的新上传或即时资讯。
        适用于监控 arXiv、bioRxiv、机构公告的即时更新。
        """
        print(f"--- TOOL: 追踪最新预印本 (query: {query}) ---")
        return self._search_internal(query=query, time_range='d', max_results=10)

    def search_recent_publications(self, query: str) -> TavilyResponse:
        """
        【工具】回顾近期成果: 检索过去一周的新论文、项目公告和合作动态。
        适用于周度科研通报或例会准备。
        """
        print(f"--- TOOL: 回顾近期成果 (query: {query}) ---")
        return self._search_internal(query=query, time_range='w', max_results=10)

    def search_visual_resources(self, query: str) -> TavilyResponse:
        """
        【工具】搜集科研视觉素材: 查找与课题相关的图表、海报、实验照片。
        适用于报告展示或科研宣传页配图。
        """
        print(f"--- TOOL: 搜集科研视觉素材 (query: {query}) ---")
        return self._search_internal(
            query=query, include_images=True, include_image_descriptions=True, max_results=5
        )

    def search_publications_by_date(self, query: str, start_date: str, end_date: str) -> TavilyResponse:
        """
        【工具】按日期回溯成果: 在明确的历史区间内检索学术成果或机构动态。
        这是唯一需要提供起止日期的工具，可用于回顾某个合作阶段或项目周期。
        """
        print(f"--- TOOL: 按日期回溯成果 (query: {query}, from: {start_date}, to: {end_date}) ---")
        return self._search_internal(
            query=query, start_date=start_date, end_date=end_date, max_results=15
        )


# --- 3. 测试与使用示例 ---

def print_response_summary(response: TavilyResponse):
    """简化的打印函数，用于展示测试结果，现在会显示成果发布日期"""
    if not response or not response.query:
        print("未能获取有效响应。")
        return
        
    print(f"\n查询: '{response.query}' | 耗时: {response.response_time}s")
    if response.answer:
        print(f"AI摘要: {response.answer[:120]}...")
    print(f"找到 {len(response.results)} 条网页, {len(response.images)} 张图片。")
    if response.results:
        first_result = response.results[0]
        date_info = f"(发布于: {first_result.published_date})" if first_result.published_date else ""
        print(f"第一条结果: {first_result.title} {date_info}")
    print("-" * 60)


if __name__ == "__main__":
    # 在运行前，请确保您已设置 TAVILY_API_KEY 环境变量
    
    try:
        # 初始化科研情报客户端，它内部包含了所有工具
        agency = TavilyAcademicAgency()

        # 场景1: Agent 进行一次常规、快速的科研检索
        response1 = agency.basic_scholarly_scan(query="量子纠缠 分布式量子计算", max_results=5)
        print_response_summary(response1)

        # 场景2: Agent 需要全面了解“全球芯片技术竞争”的科研脉络
        response2 = agency.deep_research_review(query="全球芯片技术竞争")
        print_response_summary(response2)

        # 场景3: Agent 需要追踪“NeurIPS 2025”的最新预印本
        response3 = agency.search_latest_preprints(query="NeurIPS 2025 diffusion model")
        print_response_summary(response3)

        # 场景4: Agent 需要为一篇关于“自动驾驶”的周报查找近期论文
        response4 = agency.search_recent_publications(query="自动驾驶 感知 模型 2025")
        print_response_summary(response4)

        # 场景5: Agent 需要搜集“韦伯太空望远镜”相关图像素材
        response5 = agency.search_visual_resources(query="James Webb Space Telescope discoveries")
        print_response_summary(response5)

        # 场景6: Agent 需要回溯2025年第一季度关于“人工智能法规”的政策与论文
        response6 = agency.search_publications_by_date(
            query="人工智能 法规 政策",
            start_date="2025-01-01",
            end_date="2025-03-31"
        )
        print_response_summary(response6)

    except ValueError as e:
        print(f"初始化失败: {e}")
        print("请确保 TAVILY_API_KEY 环境变量已正确设置。")
    except Exception as e:
        print(f"测试过程中发生未知错误: {e}")