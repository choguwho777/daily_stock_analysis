import os
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import time
import datetime
import requests

from google import genai
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
client = genai.Client(api_key = GEMINI_API_KEY)

from PIL import Image

FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY')

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from google.genai.errors import ClientError
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
RECEIVER_EMAIL = os.environ.get('RECEIVER_EMAIL')
APP_PASSWORD = os.environ.get('APP_PASSWORD')

## RSI 계산 함수 정의
def calculate_RSI(df, period = 14):
  delta = df['Close'].diff() # 전일 대비 가격 변화량

  up = delta.clip(lower = 0) # 주가 상승분
  down = -1 * delta.clip(upper = 0) # 주가 하락분

  EMA_up = up.ewm(com = period - 1, adjust = False).mean() # EMA 상승분
  EMA_down = down.ewm(com = period - 1, adjust = False).mean() # EMA 하락분

  RS = EMA_up / EMA_down # RS 계산
  RSI = 100 - (100 / (1 + RS)) # RSI 계산

  return RSI

## 기업 및 시장 데이터 수집 함수 정의
def get_fundamental_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    def safe_pct(val):
        return f"{val * 100:.2f}%" if val is not None else "N/A"
    def safe_num(val, fmt="{:.2f}"):
        return fmt.format(val) if val is not None else "N/A"

    fundamental = {
    "sector": info.get("sector", "N/A"),
    "industry": info.get("industry", "N/A"),
    "company_name": info.get("shortName", ticker_symbol),
    "per": safe_num(info.get("trailingPE")),
    "pbr": safe_num(info.get("priceToBook")),
    "roe": safe_pct(info.get("returnOnEquity")),
    "op_margin": safe_pct(info.get("operatingMargins")),
    "rev_growth": safe_pct(info.get("revenueGrowth")),
    "debt_to_equity": safe_num(info.get("debtToEquity")),
    "market_cap": f"{info.get('marketCap', 0) / 1e9:.2f}B USD" if info.get('marketCap') else "N/A"
  }
    return fundamental

## 뉴스 수집 함수 정의
def get_finnhub_news(ticker_symbol, limit = 3):
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days = 3)).strftime('%Y-%m-%d')
    to_date = today.strftime('%Y-%m-%d')

    url = f"https://finnhub.io/api/v1/company-news?symbol={ticker_symbol}&from={from_date}&to={to_date}&token={FINNHUB_API_KEY}"

    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return f"뉴스 수집 실패 (HTTP status: {res.status_code})\n"

        news_data = res.json()
        if not news_data:
            return "최근 관련 뉴스 없음\n"

        news_summary = ""
        for i, news in enumerate(news_data[:limit], 1):
            headline = news.get('headline', '제목 없음')
            summary = news.get('summary', '')[:100]
            news_summary += f"{i}. {headline}\n   - {summary}...\n"

        return news_summary if news_summary else "최근 관련 뉴스 없음\n"

    except Exception as e:
        return f"뉴스 수집 중 오류 발생: {e}\n"

## 이메일 발송 함수 정의
def send_email_report(report_list):
  msg = MIMEMultipart("related")
  msg['From'] = SENDER_EMAIL
  msg['To'] = RECEIVER_EMAIL
  today_str = datetime.date.today().strftime('%y%m%d')
  msg['Subject'] = f"[{today_str}] 미국 주식 분석 리포트({len(report_list)}개 종목)"
  msg_alt = MIMEMultipart("alternative")
  msg.attach(msg_alt)
  # HTML 본문
  html_section = []
  for item in report_list:
    t_symbol = item['ticker']
    reason_str = ", ".join(item['reason'])
    formatted_text = item['text'].replace("\n", "<br>")
    cid_id = f"{t_symbol}_chart"

    section = f"""
    <div style="border: 1px solid #ddd; padding: 15px; margin-bottom: 25px; border-radius: 8px; background-color: #fcfcfc;">
      <h2 style="color: #1a73e3; margin-top: 0;">[{t_symbol}] {reason_str}</h2>
      <div style="line-height: 1.6; font-size: 14px; color: #333;">
        {formatted_text}
      </div>
      <br>
      <div style="text-align: center;">
        <img src="cid:{cid_id}" style="max-width: 100%; height: auto; border: 1px solid #ccc; border-radius: 4px;">
      </div>
    </div>
    """
    html_section.append(section)

  full_html = f"""
  <html>
    <body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
      <h1 style="text-align: center; color: #222;">미국 주식 분석 리포트</h1>
      <p style="text-align: center; color: #666;">오늘 시장에서 특이 신호가 발견된 종목의 차트 및 분석 리포트입니다.</p>
      <hr style="border: 0; height: 1px; background: #ccc; margin: 20px 0;">
      {"".join(html_section)}
    </body>
  </html>
  """
  msg_alt.attach(MIMEText(full_html, "html", "utf-8"))
  # 차트 이미지 삽입
  for item in report_list:
    t_symbol = item['ticker']
    cid_id = f"{t_symbol}_chart"
    image_path = item['image_path']
    try:
      with open(image_path, "rb") as f:
        img = MIMEImage(f.read())
        img.add_header("Content-ID", f"<{cid_id}>")
        msg.attach(img)
    except Exception as e:
      print(f"{t_symbol} 이미지 첨부 실패: {e}")
  # SMTP 메일 발송
  try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
      server.login(SENDER_EMAIL, APP_PASSWORD)
      server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
    print(f"\n[{RECEIVER_EMAIL}] 메일 발송 완료")
  except Exception as e:
    print(f"\n메일 발송 실패: {e}")

## 스캔 대상 설정
watchlist = [ "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMT", "AMZN",
              "AVGO", "AXP", "BA", "BAC", "BNY", "BKNG", "BLK", "BMY", "C", "CAT",
              "CHTR", "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS", "CVX",
              "DE", "DHR", "DIS", "DOW", "DUK", "EMR", "F", "FDX", "GD", "GE",
              "GILD", "GM", "GOOG", "GOOGL", "GS", "HD", "HON", "IBM", "INTC", "INTU",
              "JNJ", "JPM", "KHC", "KO", "LIN", "LLY", "LMT", "LOW", "LRCX", "MA",
              "MCD", "MDLZ", "MDT", "MET", "META", "MMM", "MO", "MRK", "MS", "MSFT",
              "NEE", "NFLX", "NKE", "NOW", "NVDA", "ORCL", "PEP", "PFE", "PG", "PM",
              "PYPL", "QCOM", "RTX", "SBUX", "SCHW", "SO", "SPGI", "T", "TFC", "TMO",
              "TMUS", "TSLA", "TXN", "UNH", "UNP", "UPS", "USB", "V", "VZ", "WFC",
              "WMT", "XOM" ]
scanned_target = []
print("S&P 100 종목 스캔 시작")
for ticker_symbol in watchlist:
  try:
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(period = "6mo", interval = "1d")

    if df.empty or len(df) < 30:
      continue

    ## 지표 계산
    # 이동평균선
    df['MA_S'] = df['Close'].rolling(window = 5).mean()
    df['MA_L'] = df['Close'].rolling(window = 20).mean()
    # 볼린저 밴드
    std = df['Close'].rolling(window = 20).std() # 표준편차
    df['MB'] = df['Close'].rolling(window = 20).mean() # MIDDLE BAND
    df['UB'] = df['MB'] + (std * 2) # UPPER BAND
    df['LB'] = df['MB'] - (std * 2) # LOWER BAND
    # RSI
    df['RSI'] = calculate_RSI(df, period = 14)
    # 최신 데이터 추출
    yesterday_MA_S = df['MA_S'].iloc[-2]
    yesterday_MA_L = df['MA_L'].iloc[-2]
    today_MA_S = df['MA_S'].iloc[-1]
    today_MA_L = df['MA_L'].iloc[-1]

    today_CLOSE = df['Close'].iloc[-1]
    today_LB = df['LB'].iloc[-1]
    today_UB = df['UB'].iloc[-1]

    today_RSI = df['RSI'].iloc[-1]

    ## 스캔 조건문 적용
    reason = []
    # 이동평균선
    if yesterday_MA_S <= yesterday_MA_L and today_MA_S > today_MA_L:
      reason.append("이동평균선 골든크로스")
    # 볼린저 밴드
    if today_CLOSE <= today_LB:
      reason.append("볼린저 밴드 하단 이탈(과매도)")
    elif today_CLOSE >= today_UB:
      reason.append("볼린저 밴드 상단 돌파(과매수/강한 상승 모멘텀)")
    # RSI --- 조건 임시 제외 --- 260811
    # if today_RSI <= 30:
      # reason.append(f"RSI 과매도({today_RSI:.1f})")
    # elif today_RSI >= 70:
      # reason.append(f"RSI 과매수({today_RSI:.1f})")
    # 분석 리스트 추가
    if reason: scanned_target.append({'ticker': ticker_symbol, 'reason': reason, 'df': df, 'ticker_obj': ticker})
  except Exception as e:
    continue

### 리포트 생성
print(f"{len(scanned_target)}개 종목에서 특이 신호 발견")
all_report = []

## 시장 상황 분석 - 받아보고 길면 2~3줄 요약으로 반영
# 마크로 데이터 수집
try:
    tnx = yf.Ticker("^TNX").history(period="1d")['Close'].iloc[-1]
    spx = yf.Ticker("^GSPC").history(period="5d")['Close']
    vix = yf.Ticker("^VIX").history(period="1d")['Close'].iloc[-1]
    spx_return = ((spx.iloc[-1] - spx.iloc[0]) / spx.iloc[0]) * 100
    macro_info = {"us10y": f"{tnx:.2f}%", "vix": f"{vix:.2f}", "sp500_1w_change": f"{spx_return:+.2f}%"}
except Exception as e:
    print(f"마크로 데이터 수집 실패: {e}")
    macro_info = {"us10y": "N/A", "vix": "N/A", "sp500_1w_change": "N/A"}

prompt = f"""
당신은 증권사 매크로 분석가입니다.
제공된 증시 지표를 바탕으로 현재 증시 상황을 분석하세요.

[증시 지표]
- 미국 10년물 국채 금리: {macro_info['us10y']}
- VIX 지수(공포 지수): {macro_info['vix']}
- S&P 500 최근 1주 변동률: {macro_info['sp500_1w_change']}

[분석 요구 사항]
1. 유동성 국면, 경기 사이클, 금리 환경 기준으로 현재 증시 상황을 평가하세요.
2. 지금이 공격적 자산 투자 국면인지, 방어적 자산이 유리한 국면인지 판단하세요.
3. 현재 금리, 물가, 통화정책 변화가 증시 상황에 미치는 영향을 인과관계를 중심으로 설명하세요.

[형식 요구 사항]
- 첫 줄은 '[매크로 및 증시 상황]'으로 시작하세요.(인삿말, 서론 등 도입부 문장을 출력하지 마세요.)
- '**'(볼드체), '---'(구분선), '##'(헤더)와 같은 마크다운 문법을 사용하지 마세요.
- 항목 구분 시 [1. 차트 분석], [2. 뉴스 해석]과 같은 괄호와 번호를 사용하세요.
- 각 항목, 문단은 한 줄 공백(줄바꿈)으로만 자연스럽게 구분하세요.(두 줄 공백은 사용하지 마세요.)
"""
response = client.models.generate_content(model = 'gemini-3.6-flash', contents = [prompt])
all_report.append({'type': 'macro', 'text': response.text})

for target in scanned_target:
  t_symbol = target['ticker']
  t_reason = target['reason']
  df = target['df']
  ticker = target['ticker_obj']

  ## 차트 표현
  # 구역 분할 설정
  fig, (ax1, ax2) = plt.subplots(nrows = 2, ncols = 1, figsize = (6, 4), sharex = True, gridspec_kw={'height_ratios': [3, 1]})
  # 차트 제목 삽입
  plt.suptitle(f"[{t_symbol}] CHART", fontsize = 15, fontweight = 'bold')
  # ax1 / 종가, 이동평균선
  ax1.plot(df.index, df['Close'], label = 'CLOSE PRICE', color = 'black', alpha = 0.8, linewidth = 1.5)
  ax1.plot(df.index, df['MA_S'], label = 'MA(5)', color = 'blue', linestyle = '--', linewidth = 1)
  ax1.plot(df.index, df['MA_L'], label = 'MA(20) / MIDDLE BAND', color = 'brown', linestyle = '--', linewidth = 1.2)
  # ax1 / 볼린저 밴드
  ax1.plot(df.index, df['UB'], label = 'UPPER BAND', color = 'gray', linestyle = ':', alpha = 0.7)
  ax1.plot(df.index, df['LB'], label = 'LOWER BAND', color = 'gray', linestyle = ':', alpha = 0.7)
  ax1.fill_between(df.index, df['UB'], df['LB'], color = 'gray', alpha = 0.1)
  # ax1 / 세부 설정
  ax1.set_ylabel("PRICE($)")
  ax1.legend(loc = 'upper left')
  ax1.grid(True, alpha = 0.3)
  # ax2 / RSI
  ax2.plot(df.index, df['RSI'], label = 'RSI(14)', color = 'black', linewidth = 1.2)
  ax2.axhline(70, label = 'OVER BOUGHT(70)', color = 'red', linestyle = '--', alpha = 0.6)
  ax2.axhline(30, label = 'OVER SOLD(30)', color = 'blue', linestyle = '--', alpha = 0.6)
  ax2.fill_between(df.index, df['RSI'], 70, where=(df['RSI'] >= 70), color = 'red', alpha = 0.2)
  ax2.fill_between(df.index, df['RSI'], 30, where=(df['RSI'] <= 30), color = 'blue', alpha = 0.2)
  # ax2 / 세부 설정
  ax2.set_ylabel("RSI")
  ax2.set_ylim(0, 100)
  ax2.legend(loc = 'upper left')
  ax2.grid(True, alpha = 0.3)
  # 여백 최적화
  plt.tight_layout()
  # 차트 저장
  chart_filename = f"{t_symbol}_chart.png"
  plt.savefig(chart_filename, dpi = 150, bbox_inches = 'tight')
  plt.close()

  chart_img = Image.open(chart_filename)

  ## 종합 분석
  # 기업 및 시장 데이터 수집
  fund = get_fundamental_data(t_symbol)
  # 뉴스 수집
  news_summary = get_finnhub_news(t_symbol, limit = 3)
  # Gemini 분석
  prompt = f"""
당신은 증권사 기술적 분석가입니다.
오늘 스캔 결과 [{fund['company_name']}, {t_symbol}] 종목에서 다음과 같은 특이 신호가 발견되었습니다.
- 내용: {', '.join(t_reason)}

개인투자자 관점보다는 기관투자자 기준으로 분석하세요.
기술적 차트 분석은 첨부된 차트 이미지만을 근거로 분석하세요.
확인되지 않은 수급, 실적, 공시, 뉴스 내용을 임의로 생성하지 마세요.
모든 분석 및 판단에는 제공된 정보를 포함하여 출처가 명확한 자료만을 활용하세요.

[기업 및 시장 데이터]
- 기업 / 티커: {fund['company_name']} / {t_symbol}
- 섹터 / 산업: {fund['sector']} / {fund['industry']}
- 시가총액: {fund['market_cap']}
- 밸류에이션: PER({fund['per']}), PBR({fund['pbr']})
- 수익성 / 성장성: ROE({fund['roe']}), 영업이익률({fund['op_margin']}), 매출 성장률({fund['rev_growth']})
- 재무 안정성: 부채 비율({fund['debt_to_equity']}%)

[최근 뉴스(Finnhub 제공)]
{news_summary}

[분석 요구 사항]
1. 차트 분석: 첨부된 차트 이미지에서 최근 몇 달간의 주가 추세, 이동평균선들의 격차(확장/축소), 볼린저 밴드 폭의 변화, RSI 궤적을 직접 읽어내고 기술적으로 종합 설명하세요.
2. 뉴스 해석: 관련 뉴스 헤드라인이 차트 신호에 미칠 영향(긍정/부정)을 해석하고, 해당 뉴스 헤드라인을 직접 인용하세요.
3. 리스크 분석: 해당 기업 투자 시 가장 주의해야 할 리스크 3가지(구조적, 정책/규제, 실적 훼손 등)를 제시하세요.
4. 기업 구조 분석: 제공된 재무 지표(영업이익률, ROE, 부채비율 등)를 바탕으로 기업의 재무 안정성과 캐시카우 특성을 설명하세요.
5. 산업 구조 분석: 차트 이미지의 주요 지지선/저항선 가격을 기준으로, 단기/중장기 관점의 현실적인 매수가/목표가/손절가 수치와 근거를 제시하세요.

[형식 요구 사항]
- 첫 줄은 '[{fund['company_name']}, {t_symbol}]' 형식으로 시작하세요.(인삿말, 서론 등 도입부 문장을 출력하지 마세요.)
- '**'(볼드체), '---'(구분선), '##'(헤더)와 같은 마크다운 문법을 사용하지 마세요.
- 항목 구분 시 [1. 차트 분석], [2. 뉴스 해석]과 같은 괄호와 번호를 사용하세요.
- 각 항목, 문단은 한 줄 공백(줄바꿈)으로만 자연스럽게 구분하세요.(두 줄 공백은 사용하지 마세요.)
"""
  ## 메일 발송
  success = False
  retries = 0

  while not success and retries < 3:
    # 정상 작동(발송할 데이터 수집)
    try:
      response = client.models.generate_content(model = 'gemini-3.6-flash', contents = [chart_img, prompt])
      all_report.append({'ticker': t_symbol, 'reason': t_reason, 'text': response.text, 'image_path': chart_filename})
      print(f"[{t_symbol}] 분석 성공")
      success = True
    # 오류 처리
    except ClientError as e:
      if "429" in str(e):
        retries += 1
        print(f"[{t_symbol}] API 한도 초과(429) / 10초 대기 중({retries}/3)")
        time.sleep(10)
      else:
        print(f"[{t_symbol}] API 오류: {e}")
        break
    except Exception as e:
      print(F"[{t_symbol}] 알 수 없는 오류: {e}")
      break

  time.sleep(4)
# 분석 완료 후 메일 발송
if all_report:
  send_email_report(all_report)
else:
  print("분석 종목 없음")
