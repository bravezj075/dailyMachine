import os
import datetime
import requests
import arxiv
import feedparser
import time
from openai import OpenAI

# ================= 配置区域 =================

# 1. 关键词策略 (保持不变)
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

# 2. RSS 源 (保持不变)
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://techcrunch.com/category/fintech/feed/",
    "https://techcrunch.com/category/ecommerce/feed/",
    "https://www.infoq.cn/feed",
]

# 3. 您的角色上下文
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

# ================= 核心修改点：适配豆包 (火山引擎) =================

# 1. 获取 Endpoint ID (这是豆包特有的)
DOUBAO_MODEL = os.environ.get("DOUBAO_ENDPOINT_ID") 

# 2. 初始化客户端 (指向火山引擎的 Base URL)
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url="https://ark.cn-beijing.volces.com/api/v3" # 火山引擎官方兼容接口
)

WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# ================= 抓取函数 (保持不变) =================

def fetch_hacker_news():
    print("正在抓取 Hacker News...")
    articles = []
    query_str = " OR ".join([f'"{k}"' for k in ALL_KEYWORDS[:5]])
    url = f"http://hn.algolia.com/api/v1/search_by_date?query={query_str}&tags=story&numericFilters=created_at_i>{UNIX_TIMESTAMP_YESTERDAY}"
    try:
        res = requests.get(url).json()
        for hit in res.get('hits', [])[:5]:
            articles.append({
                "source": "Hacker News",
                "title": hit.get('title'),
                "url": hit.get('url', f"https://news.ycombinator.com/item?id={hit.get('objectID')}"),
                "summary": "N/A"
            })
    except Exception as e:
        print(f"HN 抓取异常: {e}")
    return articles

def fetch_arxiv_papers():
    print("正在抓取 ArXiv...")
    papers = []
    search_query = " OR ".join([f'(ti:"{k}" OR abs:"{k}")' for k in KEYWORDS_TECH])
    try:
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
        print(f"ArXiv 抓取异常: {e}")
    return papers

def fetch_rss_feeds():
    print("正在抓取 RSS...")
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
            print(f"RSS {feed_url} 抓取异常: {e}")
    return articles

# ================= 分析与推送 =================

def analyze_and_summarize(content_list):
    if not content_list:
        return None

    raw_text = ""
    for idx, item in enumerate(content_list):
        raw_text += f"{idx+1}. [{item['source']}] {item['title']}\n链接: {item['url']}\n摘要: {item['summary']}\n\n"

    print(f"正在调用豆包 ({DOUBAO_MODEL}) 分析 {len(content_list)} 条内容...")
    
    # --- 修改点 1: 优化 Prompt，适配飞书格式 ---
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
        
        # --- 修改点 2: 强制代码清洗 (防止 AI 不听话) ---
        # 如果 AI 还是输出了 ###，我们强制把它删掉，或者替换为加粗
        content = content.replace("### ", "").replace("## ", "").replace("###", "")
        
        return content
    except Exception as e:
        print(f"LLM 调用失败: {e}")
        return None

def send_notification(content):
    if not content: return
    
    title = f"📅 CTO 早报 | {datetime.date.today()}"
    msg = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"content": title, "tag": "plain_text"}},
            "elements": [{"tag": "markdown", "content": content}]
        }
    }
    if "hooks.slack.com" in WEBHOOK_URL:
        msg = {"text": f"*{title}*\n\n{content}"}

    try:
        requests.post(WEBHOOK_URL, json=msg)
        print("✅ 推送成功")
    except Exception as e:
        print(f"推送失败: {e}")

if __name__ == "__main__":
    hn = fetch_hacker_news()
    arxiv = fetch_arxiv_papers()
    rss = fetch_rss_feeds()
    all_data = hn + arxiv + rss
    
    if all_data:
        report = analyze_and_summarize(all_data)
        if report and "今日无高价值更新" not in report:
            send_notification(report)
    else:
        print("未抓取到任何数据。")
