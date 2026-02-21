import os
import json
import time
import re
import requests
import feedparser
import trafilatura
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# =========================================================
# [설정 구역]
# =========================================================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BLOG_ID = os.environ.get('BLOG_ID')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')

try:
    CLIENT_JSON = json.loads(os.environ.get('CLIENT_JSON', '{}'))
    TOKEN_JSON = json.loads(os.environ.get('TOKEN_JSON', '{}'))
except:
    print("⛔ 인증 토큰 로딩 실패")
    exit(1)

MODEL_NAME = "gemini-2.5-flash"

# =========================================================
# [함수 1] 테크 뉴스 리스트 가져오기
# =========================================================
def get_tech_news_list():
    print("🔍 구글 뉴스 [테크/IT] 섹션 검색...")
    rss_url = "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            return feed.entries[:5]
    except Exception as e:
        print(f"⛔ 뉴스 검색 에러: {e}")
    return []

# =========================================================
# [함수 2] 중복 확인
# =========================================================
def check_is_duplicate(service, news_title):
    try:
        posts = service.posts().list(blogId=BLOG_ID, maxResults=10).execute()
        for post in posts.get('items', []):
            if news_title in post.get('content', ''):
                return True
        return False
    except:
        return False

# =========================================================
# [함수 3] ★ 원문 크롤링
# =========================================================
def fetch_article_content(url):
    print(f"📰 기사 본문 크롤링 중...")
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False)
            if text and len(text) > 100:
                print(f"✅ 본문 {len(text)}자 추출 성공")
                return text[:2500]
        print("⚠️ 본문 추출 실패")
        return None
    except Exception as e:
        print(f"⛔ 크롤링 에러: {e}")
        return None

# =========================================================
# [함수 4] ★ 비슷한 기사 여러 개 찾기 (Plan B)
# =========================================================
def find_related_articles(target_title, all_news_list):
    print(f"🔍 비슷한 기사 찾는 중...")
    target_keywords = set(target_title.split())
    related_articles = []
    
    for news in all_news_list:
        if news.title == target_title:
            continue
        news_keywords = set(news.title.split())
        common = target_keywords & news_keywords
        if len(common) >= 2:
            related_articles.append(news)
            if len(related_articles) >= 3:
                break
    
    print(f"✅ 비슷한 기사 {len(related_articles)}개 발견")
    
    combined_content = ""
    for news in related_articles:
        try:
            downloaded = trafilatura.fetch_url(news.link)
            if downloaded:
                text = trafilatura.extract(downloaded, include_comments=False)
                if text and len(text) > 100:
                    combined_content += f"\n[관련 기사: {news.title[:50]}...]\n{text[:600]}\n"
                    print(f"  ✅ 추가 기사 크롤링 성공")
                    if len(combined_content) > 1800:
                        break
        except:
            continue
    
    if combined_content:
        print(f"✅ 총 {len(combined_content)}자 수집 완료")
        return combined_content
    return None

# =========================================================
# [함수 5] ★ AI 지식 기반 분석 (Plan C)
# =========================================================
def ask_ai_about_tech(news_title):
    print(f"🤖 AI 지식 기반으로 테크 분석 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    다음 IT/테크 뉴스에 대해 전문가 수준으로 분석해주세요:
    "{news_title}"
    
    다음 내용을 포함하여 4-5문단으로 설명:
    1. 이 뉴스의 기술적 배경과 맥락
    2. 관련된 기술 원리나 아키텍처
    3. 업계 표준과 경쟁 기술들
    4. 이 기술이 시장/소비자에게 미칠 영향
    5. 기술적 한계나 과제
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, 
                          headers={'Content-Type': 'application/json'}, timeout=20)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text) > 150:
                print(f"✅ AI 분석 {len(text)}자 생성")
                return text[:2000]
    except Exception as e:
        print(f"⚠️ AI 분석 실패: {e}")
    return None

# =========================================================
# [함수 6] ★ 기술 심층 리서치
# =========================================================
def research_tech_deeply(news_title, article_content):
    print("🔬 기술 심층 리서치 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    context = f"기사 내용: {article_content[:1500]}" if article_content else f"제목: {news_title}"
    
    prompt = f"""
    다음 테크 뉴스를 분석하여 독자들이 알아야 할 기술 지식을 정리해주세요.
    
    {context}
    
    다음 항목들을 각각 3-4문장으로 상세히 설명:
    1. 핵심 기술 원리: 작동 방식, 아키텍처, 알고리즘 등
    2. 기술 스택: 사용된 하드웨어/소프트웨어 기술
    3. 업계 맥락: 경쟁 기술, 시장 점유율, 업계 표준
    4. 전문가 평가: 기술적 장단점, 성능, 안정성
    5. 미래 전망: 3-5년 후 진화 방향
    
    JSON으로 출력:
    {{
      "tech_principle": "...",
      "tech_stack": "...",
      "industry_context": "...",
      "expert_evaluation": "...",
      "future_outlook": "..."
    }}
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, 
                          headers={'Content-Type': 'application/json'}, timeout=15)
        if res.status_code == 200:
            raw = res.json()['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                print("✅ 기술 리서치 완료")
                return data
    except Exception as e:
        print(f"⚠️ 리서치 실패: {e}")
    return None

# =========================================================
# [함수 7] 키워드 추출
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"'{news_title}' 뉴스의 핵심 영어 테크 키워드 3개만 콤마로. 단어만."
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, 
                           headers={'Content-Type': 'application/json'}, timeout=10)
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "technology, innovation"

# =========================================================
# [함수 8] 이미지 검색
# =========================================================
def get_relevant_images_webp(query):
    if not PEXELS_API_KEY:
        return []
    print(f"🖼️ Pexels 이미지 검색: {query}")
    try:
        resp = requests.get("https://api.pexels.com/v1/search", 
                          headers={"Authorization": PEXELS_API_KEY}, 
                          params={"query": query, "per_page": 2, "orientation": "landscape"}, 
                          timeout=10)
        if resp.status_code == 200:
            return [p['src']['original'] + "?auto=compress&fm=webp&w=800" 
                   for p in resp.json().get('photos', [])]
    except Exception as e:
        print(f"⛔ 이미지 검색 에러: {e}")
    return []

# =========================================================
# [함수 9] 마크다운 클리너
# =========================================================
def clean_markdown(text):
    text = re.sub(r'\*\*([^\*]+)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*([^\*]+)\*', r'<i>\1</i>', text)
    text = text.replace('###', '').replace('##', '').replace('#', '')
    text = text.replace('```', '').replace('**', '').replace('__', '')
    return text

# =========================================================
# [함수 10] ★ 심층 테크 칼럼 작성 (애드센스 승인용)
# =========================================================
def generate_deep_tech_content(news, images, article_content, research_data):
    print(f"🧠 AI가 심층 테크 칼럼 작성 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # 리서치 데이터 통합
    research_section = ""
    if research_data:
        research_section = f"""
[참고할 기술 지식]
- 핵심 원리: {research_data.get('tech_principle', 'N/A')}
- 기술 스택: {research_data.get('tech_stack', 'N/A')}
- 업계 맥락: {research_data.get('industry_context', 'N/A')}
- 전문가 평가: {research_data.get('expert_evaluation', 'N/A')}
- 미래 전망: {research_data.get('future_outlook', 'N/A')}
"""

    article_section = f"\n[원문 기사 발췌]\n{article_content[:1500]}\n" if article_content else ""

    prompt = f"""
    당신은 10년 경력의 IT/테크 전문 칼럼니스트입니다.
    아래 뉴스를 단순 요약이 아닌, **기술 백서 수준의 심층 해설 칼럼**으로 작성하세요.

    [뉴스 정보]
    제목: {news.title}
    링크: {news.link}
    {article_section}
    {research_section}
    
    [작성 가이드 - 애드센스 승인용]
    1. **독창성**: 다른 테크 뉴스 사이트와 완전히 다른 관점과 깊이
    2. **기술 교육**: 독자가 기술 원리를 실제로 이해할 수 있는 수준
    3. **전문성**: 기술적 정확성과 업계 맥락 제공
    4. **충분한 길이**: 최소 1500자 이상의 상세한 설명
    5. **비판적 분석**: 장점뿐 아니라 한계와 과제도 제시
    
    [HTML 구조]
    <h2>🚀 [독자의 관심을 끄는 소제목]</h2>
    <p>[이 기술이 왜 게임체인저인지 - 4문장]</p>
    
    [[IMAGE_1]]
    
    <h2>🔧 기술의 작동 원리</h2>
    <p>[핵심 기술을 비전공자도 이해할 수 있게 - 7문장 이상]</p>
    <ul>
      <li>원리 1: [알고리즘/아키텍처 설명]</li>
      <li>원리 2: [데이터 흐름/처리 과정]</li>
      <li>원리 3: [시스템 통합 방식]</li>
    </ul>
    
    <h2>💻 기술 스택과 구현</h2>
    <p>[사용된 하드웨어/소프트웨어, 프로토콜 등 - 6문장 이상]</p>
    
    [[IMAGE_2]]
    
    <h2>📊 업계 경쟁 구도</h2>
    <p>[경쟁 기술, 시장 점유율, 업계 표준 - 5문장 이상]</p>
    
    <h2>🎯 3년 후, 이 기술은</h2>
    <p>[구체적인 응용 사례와 진화 방향 - 5문장 이상]</p>
    
    <h2>⚠️ 기술적 한계와 과제</h2>
    <p>[성능 bottleneck, 호환성, 비용 등 - 4문장 이상]</p>
    
    <p><strong>결론:</strong> [핵심 메시지 2문장]</p>
    <hr>
    <p style="color:grey; font-size:0.85em;">📰 출처: <a href="{news.link}">{news.title}</a></p>
    <p style="color:grey; font-size:0.85em;">💡 본 글은 기술적 사실을 기반으로 작성되었으며, 추정 부분은 명시하였습니다.</p>
    
    [필수 규칙]
    - HTML 태그만 출력 (```html 금지)
    - 해요체 사용
    - 전문 용어는 괄호로 쉽게 풀이
    - 각 섹션 최소 4문장 이상
    - 기술적 정확성 100%
    - [[IMAGE_1]], [[IMAGE_2]]는 정확히 그대로 출력
    """
    
    for attempt in range(3):
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, 
                              headers={'Content-Type': 'application/json'}, timeout=40)
            if res.status_code == 200:
                raw = res.json()['candidates'][0]['content']['parts'][0]['text']
                clean = clean_markdown(raw)
                clean = clean.replace("```html", "").replace("```", "").strip()
                
                # 이미지 치환
                img1 = f'<img src="{images[0]}" style="width:100%; border-radius:10px; margin:20px 0;">' if len(images) > 0 else ""
                img2 = f'<img src="{images[1]}" style="width:100%; border-radius:10px; margin:20px 0;">' if len(images) > 1 else img1
                
                clean = clean.replace("[[IMAGE_1]]", img1)
                clean = clean.replace("[[IMAGE_2]]", img2)
                
                # 최소 길이 체크 (1200자 이상)
                if len(clean) > 1200:
                    print(f"✅ 글 작성 완료 ({len(clean)}자)")
                    return clean
                else:
                    print(f"⚠️ 글이 너무 짧음 ({len(clean)}자), 재시도...")
                    time.sleep(3)
                    
            elif res.status_code == 429:
                print("⏳ Rate limit, 30초 대기...")
                time.sleep(30)
        except Exception as e:
            print(f"❌ 시도 {attempt+1}/3 실패: {e}")
            time.sleep(5)
    
    return None

# =========================================================
# [함수 11] 제목 생성
# =========================================================
def generate_viral_title(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""
    '{news_title}' 뉴스의 블로그 제목 1개만.
    
    규칙:
    1. 트렌디하고 호기심 자극
    2. 괄호에 핵심 기술명
    3. 특수문자 금지
    4. 제목만 출력
    
    예: AI 시대의 심장, 엔비디아가 세상을 바꾸는 법 (GPU 혁명)
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, 
                          headers={'Content-Type': 'application/json'}, timeout=10)
        title = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        return title.split('\n')[0].replace('"', '').replace('*', '').strip()
    except:
        return news_title

# =========================================================
# [메인 실행]
# =========================================================
def run_bot():
    print("▶️ 테크 심층 분석 봇 시작 (애드센스 승인용)")
    try:
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        news_list = get_tech_news_list()
        if not news_list:
            print("❌ 뉴스 없음")
            return

        target = None
        for news in news_list:
            print(f"\n{'='*60}\n🔎 {news.title}")
            if check_is_duplicate(service, news.title):
                print("🚫 중복")
                continue
            target = news
            break
        
        if not target:
            print("😴 새 뉴스 없음")
            return

        print(f"\n✅ 선택: {target.title}\n{'='*60}\n")

        # ★★★ 3단계 폴백 시스템 ★★★
        # 1단계: 원문 크롤링
        article_content = fetch_article_content(target.link)
        
        # 2단계: 비슷한 기사들 찾기
        if not article_content:
            print("📡 Plan B: 비슷한 기사들 수집...")
            article_content = find_related_articles(target.title, news_list)
        
        # 3단계: AI 지식 기반 분석
        if not article_content:
            print("🤖 Plan C: AI 지식 기반 분석...")
            article_content = ask_ai_about_tech(target.title)
        
        # 기술 심층 리서치
        research_data = research_tech_deeply(target.title, article_content)
        
        # 이미지 검색
        keywords = get_search_keywords(target.title)
        images = get_relevant_images_webp(keywords)
        
        # 심층 칼럼 작성
        content = generate_deep_tech_content(target, images, article_content, research_data)
        
        if not content:
            print("❌ 글 작성 실패")
            return

        # 제목 생성 및 업로드
        title = generate_viral_title(target.title)
        print(f"\n📤 제목: {title}")
        
        body = {"kind": "blogger#post", "title": title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"🎉 업로드 완료! ({len(content)}자)")

    except Exception as e:
        print(f"⛔ 오류: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    run_bot()
