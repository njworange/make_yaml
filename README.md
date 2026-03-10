### YAML 생성 플러그인


다음과 TMDB 에 없는 에피소드 정보를 OTT에서 직접 가져오기 위한 플러그인이다.

기본적으로 TMDB에서 메인포스터, 에피소드별 썸네일, 공개날짜, 배우 등 정보는

IMDB에서 TMDB 봇이 잘 등록하므로 놔두고 한국어 에피소드 정보만 OTT에서 직접 가져올 목적이다.

가져온 정보가 한글이 아닐경우 만들지 않는다(티빙 어큐즈드).

추후 FF용 TMDB 쇼 파일처리에서 자동으로 만들게 할 계획이다(언제 만들지는 모른다).


######**<우선순위>**


EBSKIDS 를 제외하고 7개의 OTT 를 원하는 순서대로 넣는다.


원치 않는건 빼면 된다.


수동으로 찾을때만 해당하면 자동화시 내부자막이 있는 파일은 릴정보에 해당하는 OTT만 검색한다.


외부자막은 국내 OTT도 검색할 예정


######**<최소 매칭 점수>**


특수문자를 제외하고 매칭된다.


['로앤 오더: 성범죄 전담반', '로앤 오더 성범죄 전담반] 매칭점수는 100점이다.

['로앤 오더 성범죄 전담반', '로 앤 오더 성범죄 전담반'] 매칭점수는 96점이다.

['전생했더니 슬라임이었던 건에 대하여', '전생했더니 슬라임이었던 건에 대하여 OAD'] 매칭점수는 90점이다.


참고해서 취향대로 정한다. 실제 점수는 소수점이다.


######**<통합검색어>**

쇼의 경우는 영화하고 달리 제목이 같은 경우가 거의 없어서 특별한 경우를 제외하면 제목만으로 매칭하는데 큰 문제가 없다. 가십걸 (2007), 가십걸 (2021) 같은 경우를 위해 구분자 | 를 이용하여 연도 정보를 함께 넣을 수 있다.

모든 시즌 탐색은 티빙, 웨이브에만 해당하며 다른 OTT는 기본적으로 모든 시즌을 가져온다.

웨이브, 티빙 코드로 검색해도 검색 실패가 뜨는 경우 모든 시즌 탐색 OFF 로 한다.

웨이브 티빙의 경우 **시즌 1, 시즌 2, 1기, 2기 모두 시즌 1 ,2** 로 생성되도록 제작되었다. 특별한 경우 어쩔수 없다.

시즌 2 스페셜 이런건 시즌 0으로 본다.

웨이브 https://www.wavve.com/player/vod?programid=F3501_F35000000015 에서 ***F3501_F35000000015***

티빙 https://www.tving.com/contents/P001565742 에서 ***P001565742***

쿠팡 https://www.coupangplay.com/titles/b2a54eec-da58-4dbd-a078-5a3fb624b78e 에서 ***b2a54eec-da58-4dbd-a078-5a3fb624b78e***

넷플릭스 https://www.netflix.com/title/81519223 에서 ***81519223***

디즈니플러스 https://www.disneyplus.com/ko-kr/series/big-bet/506cEky88AhL 에서 ***506cEky88AhL***

아마존 https://www.primevideo.com/detail/0N3EDITHIBCK6E9G5PPZZQYOGQ/ref=atv_dl_rdr 에서 ***0N3EDITHIBCK6E9G5PPZZQYOGQ***

애플 tv https://tv.apple.com/kr/show/리에종---liaison/umc.cmc.62t13xacr3mxnit5a40g8tkla 에서 ***umc.cmc.62t13xacr3mxnit5a40g8tkla***

EBSKIDS https://anikids.ebs.co.kr/anikids/program/show/10024440 에서 ***10024440***


######**<현재 구현 상태>**


현재 코드 기준으로 episode parser 가능 여부는 아래와 같다.


- 웨이브: 가능
- 티빙: 가능
- 아마존 프라임 비디오: 가능
- 애플 TV: 가능
- EBSKIDS: 가능
- 넷플릭스: 가능
- 디즈니플러스: public parser 기준으로 show-level 메타데이터까지만 확인, episode-level parser 는 아직 보류
- 쿠팡플레이: 미해결


######**<OTT별 메모>**


- 웨이브, 티빙: 기존 all season 처리 유지
- 아마존 프라임 비디오: public detail page 기반으로 title, summary, 시즌/에피소드 정보를 가져온다.
- 애플 TV: public page + 공개 메타데이터 기반으로 동작한다. 다중 시즌 수집도 반영되어 있다.
- EBSKIDS: 공개 program page와 episode detail page JSON-LD 를 사용한다. episode summary 와 날짜 prefix title 이 반영되어 있다.
- 넷플릭스: public title page 기반 parser 가 추가되어 episode title, summary, 썸네일 추출이 가능하다. 다만 현재 공개 페이지 기준으로 episode 날짜 정보는 확인하지 못했다.
- 디즈니플러스: public parser 기준으로 entity page 의 title, summary, image, year, cast 같은 show-level 메타데이터는 공개되어 있으나, episode/season payload 는 아직 확보하지 못했다. 기존 legacy provider 경로는 별도로 남아 있다.
- 쿠팡플레이: 아직 안정적인 public parser 경로를 찾지 못했다.


######**<날짜 prefix 정책>**


현재 날짜 정보를 안정적으로 얻을 수 있는 OTT 는 episode title 앞에 `YYYY.MM.DD(요일)` 형식으로 붙여 통일했다.


- 적용됨: 웨이브, 티빙, 애플 TV, EBSKIDS, 아마존 프라임 비디오(날짜가 공개되는 경우)
- 미적용: 넷플릭스(현재 공개 페이지에서 episode 날짜를 확인하지 못함), 디즈니플러스, 쿠팡플레이

