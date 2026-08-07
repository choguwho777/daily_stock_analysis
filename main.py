import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import time
import datetime
import requests

!pip install -q google-genai
from google import genai
gemini_api_key = os.environ.get('gemini_api_key')
client = genai.Client(api_key = gemini_api_key)

from PIL import Image
from IPython.display import display

finnhub_api_key = os.environ.get('finnhub_api_key')

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from google.genai.errors import ClientError
SENDER_EMAIL = "sunghyuk45@gmail.com"
APP_PASSWORD = "nctt qvgr ypiw todl"
RECEIVER_EMAIL = "sunghyuk45@gmail.com"

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

## 뉴스 수집 함수 정의
def get_finnhub_news(ticker_symbol, limit=3):
    """Finnhub API를 사용하여 최근 3일간의 종목 뉴스 가져오기"""
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days=3)).strftime('%y-%m-%d')
    to_date = today.strftime('%y-%m-%d')
    
    url = f"https://finnhub.io/api/v1/company-news?symbol={ticker_symbol}&from={from_date}&to={to_date}&token={finnhub_api_key}"
    
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
    # RSI
    if today_RSI <= 30:
      reason.append(f"RSI 과매도({today_RSI:.1f})")
    elif today_RSI >= 70:
      reason.append(f"RSI 과매수({today_RSI:.1f})")
    # 분석 리스트 추가
    if reason: scanned_target.append({'ticker': ticker_symbol, 'reason': reason, 'df': df, 'ticker_obj': ticker})
  except Exception as e:
    continue

### 리포트 생성
print(f"{len(scanned_target)}개 종목에서 특이 신호 발견")
all_report = []

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
  # 뉴스 수집
  news_summary = get_finnhub_news(t_symbol, limit = 3)
  # Gemini 분석
  prompt = f"""
당신은 증권사 기술적 분석가입니다.
오늘 스캔 결과 [{t_symbol}] 종목에서 다음과 같은 특이 신호가 발견되었습니다.
- 내용: {', '.join(t_reason)}
첨부된 차트 이미지와 뉴스 헤드라인을 종합적으로 분석하세요.
어떤 종목(기업명 포함)의 분석 결과인지만 언급하세요.
제공된 수치와 차트에서 직접 확인 가능한 사실만 기술하세요.
뉴스가 제공되지 않은 경우, 뉴스 해석 단계에서 상승/하락 원인을 추정하지 마세요.
매수가/목표가/손절가를 제시하는 경우, 근거를 함께 설명하세요.
확인되지 않은 기관 수급, 실적, 공시, 뉴스 내용을 임의로 생성하지 마세요.

[최근 뉴스(Finnhub 제공)]
{news_summary}

[분석 요구 사항]
1. 차트 분석: 단순 오늘 수치가 아닌, 최근 몇 달간 주가 추세, 이동평균선 격차(확장/축소), 볼린저 밴드 폭 변동, RSI의 최근 궤적 패턴을 이미지에서 읽어내고 종합적으로 설명하세요.
2. 뉴스 해석: 관련 뉴스 헤드라인이 이번 차트 신호에 긍정적/부정적 영향을 줄 가능성을 해석하세요. 해석을 제시할 때, 제공받은 뉴스의 헤드라인도 함께 보여주세요.
3. 종합 판단: 단기 매수 타점/관망/손절선 기준 등 현실적인 투자 가이드를 3~4줄로 요약하여 정리하세요.

[형식 요구 사항]
- '**'와 같은 강조용 볼드체 마크다운 문법을 사용하지 마세요.
- '---'와 같은 구분선 마크다운 문법을 사용하지 마세요.
- 제목이나 항복 구분 시 마크다운 헤더('##')를 사용하지 말고, [1. 차트 분석], [2. 뉴스 해석]과 같은 괄호와 번호를 사용하세요.
- 각 항목이나 문단 사이는 구분선 대신 한 줄 공백(줄바꿈)으로 자연스럽게 구분하세요. 두 줄 공백은 사용하지 마세요.
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
