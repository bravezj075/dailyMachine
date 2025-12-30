import os
import datetime
import requests
import arxiv
import feedparser
import time
from openai import OpenAI

# ================= 0. 环境依赖检查 =================
# 建议使用 python-dotenv 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ================= 1. 配置区域 =================

# 关键词策略
KEYWORDS_TECH = [
    "Large Language Models", "Generative AI", "AI Agents", 
    "RAG", "Transformer", "Vector Database"
]

KEYWORDS_BIZ = [
    "E-commerce", "Fintech", "Online Retail", 
    "Fraud Detection", "Supply Chain", "Personalized Recommendation",
    "Digital Banking", "Payment Gateway"
]

ALL_KEYWORDS = KEYWORDS_TECH + KEYWORDS_BIZ

# RSS 源
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://techcrunch.com/category/fintech/feed/",
    "https://techcrunch.com/category/ecommerce/feed/",
    "https://www.infoq.cn/feed",
]

# 您的角色上下文
COMPANY_CONTEXT = """
身份：一家互联网电商与金融科技公司的 CTO。
核心关注点：
1. **AI 落地**: 如何用 LLM/Agent 提升客服效率、优化搜索推荐。
2. **金融风控**: 新的反欺诈技术、合规科技。
3. **竞品动态**: 亚马逊、Shopify、Stripe、支付宝的技术动作。
"""

# 时间设置
YESTERDAY = datetime.datetime.now() - datetime.timedelta(days=1)
UNIX_TIMESTAMP_YESTERDAY = int(time.mktime(YESTERDAY.timetuple()))

# API 配置 (请确保环境变量已设置)
DOUBAO_MODEL = os.environ.get("DOUBAO_ENDPOINT_ID") # 例如 ep-2024...
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# 初始化客户端 (火山引擎)
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://ark.cn-beijing.volces.com/api/v3"
)

# ================= 2. 抓取函数 =================

def fetch_hacker_news():
    print("🔍 正在抓取 Hacker News...")
    articles = []
    query_str = " OR ".join([f'"{k}"' for k in ALL_KEYWORDS[:5]])
    url = f"http://hn.algolia.com/api/v1/search_by_date?query={query_str}&tags=story&numericFilters=created_at_i>{UNIX_TIMESTAMP_YESTERDAY}"
    try:
        res = requests.get(url, timeout=10).json()
        for hit in res.get('hits', [])[:5]:
            articles.append({
                "source": "Hacker News",
                "title": hit.get('title'),
                "url": hit.get('url', f"https://news.ycombinator.com/item?id={hit.get('objectID')}"),
                "summary": "N/A"
            })
    except Exception as e:
        print(f"❌ HN 抓取异常: {e}")
    return articles

def fetch_arxiv_papers():
    print("🔍 正在抓取 ArXiv...")
    papers = []
    # 构造查询：cs.AI 类别 AND (关键词)
    search_query = " OR ".join([f'(ti:"{k}" OR abs:"{k}")' for k in KEYWORDS_TECH])
    try:
        # 注意：arxiv 库可能有 API 限制，建议生产环境增加重试机制
        search = arxiv.Search(
            query = f'cat:cs.AI AND ({search_query})',
            max_results = 5,
            sort_by = arxiv.SortCriterion.SubmittedDate
        )
        for result in search.results():
            if result.published.date() >= YESTERDAY.date():
                papers.append({
                    "source": "ArXiv",
                    "title": result.title,
                    "url": result.entry_id,
                    "summary": result.summary[:200].replace("\n", " ") + "..."
                })
    except Exception as e:
        print(f"❌ ArXiv 抓取异常: {e}")
    return papers

def fetch_rss_feeds():
    print("🔍 正在抓取 RSS...")
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                content_text = (entry.title + entry.get('summary', '')).lower()
                if any(k.lower() in content_text for k in ALL_KEYWORDS):
                    articles.append({
                        "source": f"RSS ({feed.feed.get('title', 'Media')})",
                        "title": entry.title,
                        "url": entry.link,
                        "summary": entry.get('summary', 'No summary')[:150] + "..."
                    })
        except Exception as e:
            print(f"❌ RSS {feed_url} 抓取异常: {e}")
    return articles

# ================= 3. 分析与推送 =================

def analyze_and_summarize(content_list):
    if not content_list:
        return None

    raw_text = ""
    for idx, item in enumerate(content_list):
        raw_text += f"{idx+1}. [{item['source']}] {item['title']}\n链接: {item['url']}\n摘要: {item['summary']}\n\n"

    print(f"🤖 正在调用豆包 ({DOUBAO_MODEL}) 分析 {len(content_list)} 条内容...")
    
    prompt = f"""
    你是我公司的【首席技术情报官】。
    
    【我的背景】
    {COMPANY_CONTEXT}
    
    【今日原始情报】
    {raw_text}
    
    【任务】
    请以 CTO 的战略视角审视信息，剔除噪音。
    
    【⚠️ 格式严格要求 (针对飞书渲染优化)】
    1. **绝对不要使用** Markdown 标题语法（如 #, ##, ###），因为客户端无法渲染。
    2. 所有的标题、重点，请一律使用 **双星号加粗** (例如：**标题**) 代替。
    3. 列表项请使用 emoji (🔹) 或圆点 (•) 开头。
    4. 每个板块之间请留出空行。
    
    【目标输出样式模板】
    **🚀 行业与业务动态**
    
    **[标题文本](链接URL)**
    • **情报**: 这里写摘要...
    • **CTO 洞察**: 这里写分析...
    
    (空一行)
    
    **⚡ 技术前沿**
    
    **[标题文本](链接URL)**
    • **情报**: 这里写摘要...
    • **CTO 洞察**: 这里写分析...
    
    如果全是噪音，回复“今日无高价值更新”。
    """

    try:
        response = client.chat.completions.create(
            model=DOUBAO_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        content = response.choices[0].message.content
        
        # --- 数据清洗 ---
        # 1. 移除 Markdown 标题符，防止格式错乱
        content = content.replace("### ", "").replace("## ", "").replace("###", "")
        # 2. 优化列表间距，确保飞书渲染不拥挤
        content = content.replace("\n•", "\n\n•").replace("\n🔹", "\n\n🔹")
        
        return content
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        return None

def send_notification(content):
    if not content: return
    
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    title = f"📅 CTO 早报 | {today_str}"
    
    # 构造飞书交互式卡片
    msg = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "content": title,
                    "tag": "plain_text"
                }
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": content
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "Powered by Doubao & Feishu Bot"
                        }
                    ]
                }
            ]
        }
    }

    # 兼容 Slack (如果 URL 包含 slack)
    if WEBHOOK_URL and "hooks.slack.com" in WEBHOOK_URL:
        msg = {"text": f"*{title}*\n\n{content}"}

    try:
        # ✅ 关键修正：直接使用 json=msg，不要 json.dumps
        resp = requests.post(WEBHOOK_URL, json=msg)
        resp.raise_for_status() # 检查 HTTP 错误
        print(f"✅ 推送成功! 响应: {resp.json()}")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

# ================= 4. 主程序入口 =================

if __name__ == "__main__":
    if not WEBHOOK_URL or not DOUBAO_MODEL:
        print("⚠️ 警告: 环境变量 WEBHOOK_URL 或 DOUBAO_ENDPOINT_ID 未设置，程序可能无法正常工作。")

    print("🚀 任务开始...")
    
    # 1. 获取数据
    hn_data = fetch_hacker_news()
    # ⚠️ 修正：变量名改为 arxiv_data，避免覆盖导入的 arxiv 模块
    arxiv_data = fetch_arxiv_papers() 
    rss_data = fetch_rss_feeds()
    
    all_data = hn_data + arxiv_data + rss_data
    
    if all_data:
        print(f"📊 共获取 {len(all_data)} 条原始数据，开始分析...")
        report = analyze_and_summarize(all_data)
        
        if report and "今日无高价值更新" not in report:
            send_notification(report)
        else:
            print("🔕 今日无高价值内容，跳过推送。")
    else:
        print("📭 未抓取到任何数据。")
