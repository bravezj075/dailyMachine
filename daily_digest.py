import os
import datetime
import requests
import arxiv
import feedparser
import time
from openai import OpenAI

# ================= 配置区域 =================

# 1. 关键词策略
# 技术侧：关注 AI 核心能力
KEYWORDS_TECH = [
    "Large Language Models", "Generative AI", "AI Agents", 
    "RAG", "Transformer", "Vector Database"
]

# 业务侧：关注 电商 & 金融 场景
KEYWORDS_BIZ = [
    "E-commerce", "Fintech", "Online Retail", 
    "Fraud Detection", "Supply Chain", "Personalized Recommendation",
    "Digital Banking", "Payment Gateway"
]

# 合并用于混合搜索
ALL_KEYWORDS = KEYWORDS_TECH + KEYWORDS_BIZ

# 2. 商业媒体 RSS 源 (捕捉行业动态)
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://techcrunch.com/category/fintech/feed/",
    "https://techcrunch.com/category/ecommerce/feed/",
    "https://www.infoq.cn/feed", # InfoQ 中文站 (可选，覆盖架构与技术管理)
]

# 3. 您的角色上下文 (AI 筛选的核心依据)
COMPANY_CONTEXT = """
身份：一家互联网电商与金融科技公司的 CTO。
核心关注点：
1. **AI 落地**: 如何用 LLM/Agent 提升客服效率、优化搜索推荐、生成营销内容。
2. **金融风控**: 新的反欺诈技术、合规科技、支付安全。
3. **竞品动态**: 亚马逊、Shopify、Stripe、支付宝等巨头的最新技术动作。
4. **架构演进**: 降本增效，从单体向微服务/Serverless 的迁移与治理。
"""

# 时间设置
YESTERDAY = datetime.datetime.now() - datetime.timedelta(days=1)
UNIX_TIMESTAMP_YESTERDAY = int(time.mktime(YESTERDAY.timetuple()))

# 初始化客户端
# client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
# 修改为 👇 (注意 base_url)
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"), # 这里的 Key 换成 DeepSeek 的
    base_url="https://api.deepseek.com"       # 指向 DeepSeek 的服务器
)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# ================= 抓取函数 =================

def fetch_hacker_news():
    """Hacker News: 侧重技术社区的深度讨论"""
    print("正在抓取 Hacker News...")
    articles = []
    # 为了避免 URL 过长，只取最重要的前 5 个关键词进行 HN 搜索
    query_str = " OR ".join([f'"{k}"' for k in ALL_KEYWORDS[:5]])
    
    url = f"http://hn.algolia.com/api/v1/search_by_date?query={query_str}&tags=story&numericFilters=created_at_i>{UNIX_TIMESTAMP_YESTERDAY}"
    
    try:
        res = requests.get(url).json()
        for hit in res.get('hits', [])[:5]:
            articles.append({
                "source": "Hacker News",
                "title": hit.get('title'),
                "url": hit.get('url', f"https://news.ycombinator.com/item?id={hit.get('objectID')}"),
                "summary": "N/A (Community Discussion)"
            })
    except Exception as e:
        print(f"HN 抓取异常: {e}")
    return articles

def fetch_arxiv_papers():
    """ArXiv: 侧重 AI 技术的最前沿理论"""
    print("正在抓取 ArXiv...")
    papers = []
    # ArXiv 只搜索技术关键词
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
    """RSS: 侧重商业落地和行业新闻"""
    print("正在抓取 RSS...")
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]: # 每个源取前3条
                content_text = (entry.title + entry.get('summary', '')).lower()
                # 简单过滤：只要包含我们关心的任一关键词
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

    print(f"正在调用 LLM 分析 {len(content_list)} 条内容...")
    
    prompt = f"""
    你是我公司的【首席技术情报官】。
    
    【我的背景】
    {COMPANY_CONTEXT}
    
    【今日原始情报】
    {raw_text}
    
    【任务】
    请以 CTO 的战略视角审视上述信息，剔除噪音，只保留对业务或技术架构有**实质影响**的内容。
    
    【输出格式 (Markdown)】
    请按照以下分类输出（如果没有相关内容，该分类可留空）：
    
    ### 🚀 行业与业务动态 (电商/金融)
    * **[标题](链接)**
      * **情报**: 一句话概括发生了什么（如：Stripe 推出了新功能...）。
      * **CTO 洞察**: 对我们业务的借鉴意义（如：我们可以模仿这个做风控...）。
    
    ### ⚡ 技术前沿 (AI/架构)
    * **[标题](链接)**
      * **情报**: 解决了什么技术难题。
      * **CTO 洞察**: 实施难度与潜在收益（如：适合作为 Q3 的技术预研项目...）。

    > **总结**: (可选) 如果有特别重大的消息，用加粗一句话提醒我。
    
    如果今天全是无关噪音，请直接回复：“今日无高价值更新。”
    """

    try:
        response = client.chat.completions.create(
           # model="gpt-4o",
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM 调用失败: {e}")
        return None

def send_notification(content):
    if not content:
        return
    
    # 标题增加日期
    title = f"📅 CTO 早报 | {datetime.date.today()}"
    
    # 适配飞书 Webhook
    msg = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"content": title, "tag": "plain_text"}},
            "elements": [{"tag": "markdown", "content": content}]
        }
    }
    
    # 简单的 Slack 兼容 (如果 URL 包含 slack)
    if "hooks.slack.com" in WEBHOOK_URL:
        msg = {"text": f"*{title}*\n\n{content}"}

    try:
        requests.post(WEBHOOK_URL, json=msg)
        print("✅ 推送成功")
    except Exception as e:
        print(f"推送失败: {e}")

# ================= 主入口 =================

if __name__ == "__main__":
    # 1. 聚合多源数据
    hn = fetch_hacker_news()
    arxiv = fetch_arxiv_papers()
    rss = fetch_rss_feeds()
    
    all_data = hn + arxiv + rss
    
    print(f"抓取结束。HN:{len(hn)}, ArXiv:{len(arxiv)}, RSS:{len(rss)}。总计: {len(all_data)}")
    
    # 2. LLM 分析
    if all_data:
        report = analyze_and_summarize(all_data)
        
        # 3. 推送结果
        if report and "今日无高价值更新" not in report:
            send_notification(report)
        else:
            print("内容经过 AI 筛选后无高价值信息，跳过推送。")
    else:
        print("未抓取到任何数据。")
