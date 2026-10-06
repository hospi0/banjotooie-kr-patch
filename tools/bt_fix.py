"""Glossary / tone correction of 하스피's Banjo-Tooie translation (반조-카주이 tools/apply_fixes.py 방식).
  in : my files/bt/*.tsv (read only)
  out: work/text/fixed/<same names> + work/text/교정_변경목록.tsv
Order: glossary (translation column; longer first; optional «only if the source has X» condition, regex
entries start with 're:') -> per-row fixes (work/text/bt_fixes.tsv: 위치 / 번역 / 이유).
Shared names follow the 반조-카주이 release (반조·멈보·클렁고·보틀스·나선산·탤런…)."""
import glob, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SRC = os.path.join(ROOT, 'my files', 'bt')
OUT = os.path.join(ROOT, 'work', 'text', 'fixed')
LOG = os.path.join(ROOT, 'work', 'text', '교정_변경목록.tsv')
FIXES = os.path.join(ROOT, 'work', 'text', 'bt_fixes.tsv')
UNIFY = os.path.join(ROOT, 'work', 'text', 'bt_unify.tsv')    # same source -> one wording (work/unify.py)

# (from, to, reason[, source must contain])
GLOSSARY = [
    ('밴조', '반조', '주인공 이름 통일(카주이와 같게)'),
    ('맘보', '멈보', '이름 통일(MUMBO=멈보, 카주이와 같게)'),
    ('클룽고', '클렁고', '이름 통일(KLUNGO=클렁고, 카주이와 같게)'),
    ('보틀즈', '보틀스', '이름 통일(BOTTLES=보틀스, 카주이와 같게)'),
    ('바틀즈', '보틀스', '이름 통일(BOTTLES=보틀스, 카주이와 같게)'),
    ('스파이럴 마운틴', '나선산', '지명 통일(SPIRAL MOUNTAIN=나선산, 카주이와 같게)'),
    ('험바 웜바', '훔바 움바', '이름 통일(HUMBA WUMBA=훔바 움바, 번역 다수 표기)'),
    ('험바', '훔바', '이름 통일(HUMBA=훔바)'),
    ('웜바', '움바', '이름 통일(WUMBA=움바)'),
    ('위그왬', '위그왐', '표기 통일(WIGWAM=위그왐)'),
    ('징걸링', '징갈링', '이름 통일(JINGALING=징갈링)'),
    ('진갈링', '징갈링', '이름 통일(JINGALING=징갈링)'),
    ('허니비', '허니 비', '이름 통일(HONEY B=허니 비)'),
    ('아일 오 해그즈', '해그 섬', '지명 통일(ISLE O\' HAGS=해그 섬, 번역 다수 표기)'),
    ('아일 오 해그스', '해그 섬', '지명 통일(해그 섬)'),
    ('마녀섬', '해그 섬', '지명 통일(해그 섬)'),
    ('마야헴 신전', '마야헴 사원', '지명 통일(MAYAHEM TEMPLE=마야헴 사원)'),
    ('졸리 로저스 라군', '졸리 로저의 라군', '지명 통일(JOLLY ROGER\'S LAGOON=졸리 로저의 라군)'),
    ('졸리 로저 라군', '졸리 로저의 라군', '지명 통일(졸리 로저의 라군)'),
    ('테리댁틸랜드', '테리닥틸랜드', '지명 통일(TERRYDACTYLAND=테리닥틸랜드)'),
    ('re:그런티 인더스트리(?!즈)', '그런티 인더스트리즈', '지명 통일(GRUNTY INDUSTRIES=그런티 인더스트리즈)'),
    ('헤일파이어 봉우리', '헤일파이어 피크스', '지명 통일(HAILFIRE PEAKS=헤일파이어 피크스)'),
    ('re:헤일파이어 피크(?!스)', '헤일파이어 피크스', '지명 통일(헤일파이어 피크스)'),
    ('진조 빌리지', '진조 마을', '지명 통일(JINJO VILLAGE=진조 마을)'),
    ('타르깃잔', '타깃잔', '이름 통일(TARGITZAN=타깃잔)'),
    ('타르기잔', '타깃잔', '이름 통일(TARGITZAN=타깃잔)'),
    ('타기잔', '타깃잔', '이름 통일(TARGITZAN=타깃잔)'),
    ('밍기 종고', '밍지 종고', '이름 통일(MINGY JONGO=밍지 종고)'),
    ('우팍팍', '우 팍 팍', '이름 통일(WOO FAK FAK=우 팍 팍)'),
    ('우 팍팍', '우 팍 팍', '이름 통일(우 팍 팍)'),
    ('카나리 메리', '카나리아 메리', '이름 통일(CANARY MARY=카나리아 메리)'),
    ('닥블룬', '더블룬', '용어 통일(DOUBLOON=더블룬)'),
    ('두블룬', '더블룬', '용어 통일(DOUBLOON=더블룬)'),
    ('줍바', '주바', '이름 통일(ZUBBA=주바)'),
    ('저바', '주바', '이름 통일(ZUBBA=주바)', 'ZUBBA'),
    ('탈론', '탤런', '기술 이름 통일(TALON=탤런, 카주이와 같게)'),
    ('탤론', '탤런', '기술 이름 통일(TALON=탤런, 카주이와 같게)'),
    ('클락워크 카주이 에그', '태엽 카주이 알', '용어 통일(CLOCKWORK KAZOOIE EGGS=태엽 카주이 알)'),
    ('클락워크', '태엽', '용어 통일(CLOCKWORK=태엽, 번역 다수 표기)'),
    ('그레네이드', '수류탄', '용어 통일(GRENADE=수류탄, 번역 다수 표기)'),
    ('위험한 접시', '위험의 접시', '놀이기구 이름 통일(SAUCER OF PERIL=위험의 접시)', 'SAUCER OF PERIL'),
    ('위험의 소서', '위험의 접시', '놀이기구 이름 통일(위험의 접시)'),
    ('글로우보', '글로보', '이름 통일(GLOWBO=글로보)'),
    ('다리 스프링', '레그 스프링', '기술 이름 통일(LEG SPRING=레그 스프링)', 'LEG SPRING'),
    ('미스터 패치', '패치 씨', '이름 통일(MR. PATCH=패치 씨)'),
    ('색 팩', '섁 팩', '기술 이름 구분(SHACK PACK=섁 팩)', 'SHACK PACK'),
    ('섁 팩', '색 팩', '기술 이름 구분(SACK PACK=색 팩)', 'SACK PACK'),
    # 2026-10-06 001 통독에서
    ('엄보', '멈보', '오타(MUMBO=멈보)'),
    ('검보', '멈보', '오타(MUMBO=멈보)'),
    ('그런트 마님', '그런티 마님', '이름 통일(GRUNTY=그런티)'),
    ('하그즈 섬', '해그 섬', '지명 통일(해그 섬)'),
    ('바틀스', '보틀스', '이름 통일(BOTTLES=보틀스)'),
    ('악보', '음표', '용어 통일(NOTES=음표)', 'NOTES'),
    ('금색 깃털', '황금 깃털', '용어 통일(GOLD FEATHERS=황금 깃털, 카주이와 같게)'),
    ('벼룩 봉지', '벼룩투성이', '어색한 직역(FLEABAG=벼룩투성이)'),
    ('조준 시야', '조준경', '어색한 직역(AIMING SIGHT=조준경)'),
    ('빅 버스터', '부리 박치기', '기술 이름 통일(BEAK BUSTER=부리 박치기, 카주이와 같게)'),
    ('부리 내리찍기 공격', '부리 박치기 공격', '기술 이름 통일(BEAK BUSTER=부리 박치기, 카주이와 같게)'),
    ('비크 바이오넷', '부리 총검', '기술 이름(BEAK BAYONET=부리 총검)'),
    ('스프링기 스텝', '스프링 스텝', '아이템 이름 통일(SPRINGY STEP SHOES=스프링 스텝 슈즈)'),
    ('에어본 에이밍', '공중 알 조준', '기술 이름 통일(AIRBORNE EGG AIMING=공중 알 조준)'),
    ('공중 조준', '공중 알 조준', '기술 이름 통일(공중 알 조준)', 'AIRBORNE'),
    ('서브아쿠아 에이밍', '수중 알 조준', '기술 이름 통일(SUB-AQUA EGG AIMING=수중 알 조준)'),
    ('에그 에임', '알 조준', '기술 이름 통일(EGG AIM=알 조준, 번역 다수 표기)'),
    ('파이어 에그', '불꽃 알', '알 이름 통일(FIRE EGGS=불꽃 알)'),
    ('수류탄 에그', '수류탄 알', '알 이름 통일(GRENADE EGGS=수류탄 알)'),
    ('아이스 에그', '얼음 알', '알 이름 통일(ICE EGGS=얼음 알)'),
    ('불꽃알', '불꽃 알', '알 이름 통일(불꽃 알)'),
    ('수류탄알', '수류탄 알', '알 이름 통일(수류탄 알)'),
    ('탈수기', '세탁기', '변신 이름 통일(WASHER=세탁기)', 'WASHER'),
    ('우디드 할로우', '숲속 골짜기', '구역 이름 통일(WOODED HOLLOW=숲속 골짜기 — 다른 구역처럼 번역)'),
    ('re:늪지(?!대)', '늪지대', '구역 이름 통일(QUAGMIRE=늪지대)', 'QUAGMIRE'),
    # 002 통독에서
    ('밍기', '밍지', '이름 통일(MINGY=밍지)'),
    ('준결승 진출전', '준준결승', '오역(QUARTERFINAL=준준결승)', 'QUARTER'),
    ('진조 킹', '진조 왕', '이름 통일(징갈링 왕)'),
    ('폰노', '포노', '이름 통일(PAWNO=포노)'),
    ('반조카주이', '반조-카주이', '표기 통일'),
    ('파트너', '짝꿍', '용어 통일(졸리·매기 PARTNER=짝꿍)', 'PARTNER'),
    ('프리지지 피크', '프리지피크', '지명 통일(FREEZEEZY PEAK=프리지피크, 카주이와 같게)'),
    ('프리지 피크', '프리지피크', '지명 통일(FREEZEEZY PEAK=프리지피크, 카주이와 같게)'),
    ('그런티 부인', '마담 그런티', '이름(MADAME GRUNTY=점쟁이 마담 그런티)', 'MADAME'),
    ('메이헴 신전', '마야 대혼란 사원', '지명 통일'),
    ('마녀의 섬', '마녀섬', '지명 통일'),
    # 2026-10-06 하스피 «투이도 마녀섬을 비롯 뜻으로 옮겨줘» — 세계 이름(위의 음역 통일 뒤에 바꾼다)
    ('해그 섬', '마녀섬', '지명 뜻으로(ISLE O\' HAGS=마녀섬, 하스피)'),
    ('마야헴 사원', '마야 대혼란 사원', '지명 뜻으로(MAYAHEM TEMPLE=마야 대혼란 사원)'),
    ('마야헴', '마야 대혼란', '지명 뜻으로(마야 대혼란 사원)'),
    ('글리터 걸치 광산', '반짝 협곡 광산', '지명 뜻으로(GLITTER GULCH MINE=반짝 협곡 광산)'),
    ('글리터 걸치', '반짝 협곡', '지명 뜻으로(반짝 협곡 광산)'),
    ('위치월드', '마녀랜드', '지명 뜻으로(WITCHYWORLD=마녀랜드)'),
    ('졸리 로저의 라군', '졸리 로저의 석호', '지명 뜻으로(JOLLY ROGER\'S LAGOON=졸리 로저의 석호)'),
    ('테리닥틸랜드', '익룡랜드', '지명 뜻으로(TERRYDACTYLAND=익룡랜드)'),
    ('그런티 인더스트리즈', '그런티 산업', '지명 뜻으로(GRUNTY INDUSTRIES=그런티 산업)'),
    ('헤일파이어 피크스', '불얼음 봉우리', '지명 뜻으로(HAILFIRE PEAKS=불얼음 봉우리)'),
    ('클라우드 쿠쿠랜드', '구름 뻐꾸기 나라', '지명 뜻으로(CLOUD CUCKOOLAND=구름 뻐꾸기 나라)'),
    ('콜드론 킵', '가마솥 성', '지명 뜻으로(CAULDRON KEEP=가마솥 성)'),
    ('위그왐', '천막', '지명 뜻으로(WUMBA\'S WIGWAM=움바의 천막)'),
    # 010 통독에서 (지명·이름 표기 통일)
    ('뭄보', '멈보', '이름 통일(MUMBO=멈보)'),
    ('제이드 스네이크', '비취뱀', '이름 뜻으로(JADE SNAKE=비취뱀)'),
    ('비취 뱀', '비취뱀', '이름 통일(비취뱀)'),
    ('옥 뱀', '비취뱀', '이름 통일(비취뱀)'),
    ('비취뱀의 숲', '비취뱀 숲', '지명 통일(JADE SNAKE GROVE=비취뱀 숲)'),
    ('오글 부글', '우글 부글', '이름 통일(OOGLE BOOGLE=우글 부글)'),
    ('챔파사우르', '촘파사우루스', '이름 통일(CHOMPASAUR=촘파사우루스)'),
    ('촘파사우르', '촘파사우루스', '이름 통일(CHOMPASAUR=촘파사우루스)'),
    ('스톰핑 플레인즈', '쿵쾅 평원', '지명 뜻으로(STOMPING PLAINS=쿵쾅 평원)'),
    ('스톰핑 평원', '쿵쾅 평원', '지명 뜻으로(STOMPING PLAINS=쿵쾅 평원)'),
    ('짓밟힌 평원', '쿵쾅 평원', '지명 뜻으로(STOMPING PLAINS=쿵쾅 평원)'),
    ('오일 드릴', '석유 시추기', '용어 통일(OIL DRILL=석유 시추기)'),
    ('석유 드릴', '석유 시추기', '용어 통일(OIL DRILL=석유 시추기)'),
    ('쿠쿠 올림픽', '뻐꾸기 올림픽', '이름 뜻으로(CUCKOO OLYMPICS, 구름 뻐꾸기 나라)'),
    ('팁탑', '팁텁', '이름 통일(TIPTUP=팁텁)'),
    ('닷지돔', '범퍼카 돔', '이름 통일(DODGEM DOME=범퍼카 돔)'),
    ('도지엠 돔', '범퍼카 돔', '이름 통일(DODGEM DOME=범퍼카 돔)'),
    ('후프 허리', '후프 질주', '이름 뜻으로(HOOP HURRY — «허리»는 몸 허리로 읽힌다)'),
    ('위험의 접시 비행선', '공포의 비행접시', '이름 뜻으로(SAUCER OF PERIL=공포의 비행접시)'),
    ('위험의 접시', '공포의 비행접시', '이름 뜻으로(SAUCER OF PERIL=공포의 비행접시)'),
    ('졸리네 가게', '졸리네', '이름 통일(JOLLY\'S=졸리네)'),
    ('졸리 가게', '졸리네', '이름 통일(JOLLY\'S=졸리네)'),
    ('졸리스', '졸리네', '이름 통일(JOLLY\'S=졸리네)'),
    ('황금 단지', '황금 항아리', '용어 통일(POT O\' GOLD=황금 항아리)'),
    (r're:을\(를\)', '을', '조사 표기 통일({86}을)'),
    ('웅가붕가', '웅가 붕가', '이름 통일(UNGA BUNGA=웅가 붕가, 우글 부글과 같게)'),
    ('잼 자스', '잼자스', '이름 통일(JAMJARS=잼자스)'),
    # 011 통독에서
    ('도지엠', '범퍼카', '이름 통일(DODGEM=범퍼카)'),
    ('졸리즈', '졸리네', '이름 통일(JOLLY\'S=졸리네)'),
    ('졸리의 주크박스', '졸리네 주크박스', '이름 통일(JOLLY\'S=졸리네)'),
    ('워딩 부츠', '웨이딩 부츠', '아이템 이름 통일(WADING BOOTS=웨이딩 부츠, 카주이와 같게)'),
    ('지기위기 사원', '지기위기 신전', '용어 통일(JIGGYWIGGY\'S TEMPLE=신전)'),
    ('지기위기의 사원', '지기위기의 신전', '용어 통일(JIGGYWIGGY\'S TEMPLE=신전)'),
    ('교도소 단지', '감옥 구역', '지명 통일(PRISON COMPOUND=감옥 구역)'),
    ('파워 오두막', '발전 오두막', '지명 통일(POWER HUT=발전 오두막)'),
    ('발전소 오두막', '발전 오두막', '지명 통일(POWER HUT=발전 오두막)'),
    ('병기 창고', '탄약 창고', '지명 통일(ORDNANCE STORAGE=탄약 창고)'),
    ('빅탑 텐트', '서커스 천막', '지명 뜻으로(BIG TOP=서커스 천막)'),
    ('빅탑', '서커스 천막', '지명 뜻으로(BIG TOP=서커스 천막)'),
    ('헌티드 동굴', '유령 동굴', '지명 뜻으로(HAUNTED CAVERN=유령 동굴)'),
    ('포노의 백화점', '포노의 상점', '이름 통일(PAWNO\'S EMPORIUM=포노의 상점)'),
    ('물고기들의 사원', '물고기 사원', '지명 통일(TEMPLE OF THE FISHES=물고기 사원)'),
    ('클링커즈', '클링커', '이름 통일(CLINKERS=클링커)'),
    # 012 통독에서 (메뉴 기술·지명을 대사 쪽 표기에 맞춘다)
    ('팩 훼크', '팩 왝', '기술 이름 통일(PACK WHACK=팩 왝)'),
    ('날개 훼크', '윙 왝', '기술 이름 통일(WING WHACK=윙 왝)'),
    ('발톱 토피도', '탤런 토피도', '기술 이름 통일(TALON TORPEDO=탤런 토피도)'),
    ('발톱 등반 부츠', '클로 클램버 부츠', '아이템 이름 통일(CLAW CLAMBER BOOTS)'),
    ('스프링 신발', '스프링 스텝 슈즈', '아이템 이름 통일(SPRINGY STEP SHOES)'),
    ('수면 팩', '스누즈 팩', '기술 이름 통일(SNOOZE PACK=스누즈 팩)'),
    ('자루 팩', '색 팩', '기술 이름 통일(SACK PACK=색 팩)'),
    ('골든 골리앗', '황금 골리앗', '이름 통일(GOLDEN GOLIATH=황금 골리앗)'),
    ('황금 거인', '황금 골리앗', '이름 통일(GOLDEN GOLIATH=황금 골리앗)'),
    ('별 회전기', '스타 스피너', '이름 통일(STAR SPINNER=스타 스피너)'),
    ('트윙클리', '반짝이', '이름 통일(TWINKLIES=반짝이, 대사 쪽 표기)'),
    ('마얀 킥볼', '마야 킥볼', '이름 통일(MAYAN KICKBALL=마야 킥볼)'),
    ('도지 챌린지', '범퍼카 챌린지', '이름 통일(DODGEM=범퍼카)'),
    ('도지 돔', '범퍼카 돔', '이름 통일(DODGEM=범퍼카)'),
    ('포탄 저장고', '탄약 창고', '지명 통일(ORDNANCE STORAGE=탄약 창고)'),
    ('총격전', '사격전', '용어 통일(SHOOTOUT=사격전)'),
    ('슈팅전', '사격전', '용어 통일(SHOOTOUT=사격전)'),
    ('re:슈팅$', '사격전', '용어 통일(SHOOTOUT=사격전)', 'SHOOTOUT'),
    ('아이시클 그로토', '고드름 동굴', '지명 통일(ICICLE GROTTO=고드름 동굴)'),
    ('타워 오브 트래저디', '비극의 탑', '이름 뜻으로(TOWER OF TRAGEDY=비극의 탑)'),
    ('디거 터널', '굴착 터널', '지명 통일(DIGGER TUNNEL=굴착 터널)'),
    ('디거 내부', '굴착기 내부', '지명 통일(DIGGER=굴착기)'),
    ('해그 1', '마녀 1호', '이름 통일(HAG 1=마녀 1호)'),
    ('샤먼', '주술사', '용어 통일(SHAMAN=주술사)'),
    ('탐광자', '탐광꾼', '용어 통일(PROSPECTOR=탐광꾼)'),
    ('캐너리 메리', '카나리아 메리', '이름 통일(CANARY MARY)'),
    ('손수레 경주', '수레 경주', '용어 통일(HANDCART RACE=수레 경주)'),
    ('노동자 숙소', '일꾼 숙소', '용어 통일(WORKERS\' QUARTERS=일꾼 숙소)'),
    ('조금 신성한 방', '살짝 신성한 방', '이름 통일(SLIGHTLY SACRED=살짝 신성한, 퀴즈 답과 같게)'),
    # 멀티플레이 게임·알 종류 이름 — 음역 대신 뜻으로
    ('스쿼크매치', '꽥꽥 대결', '이름 뜻으로(SQUAWKMATCH)'),
    ('싱글 에그 스플랫', '알 한 방', '이름 뜻으로(SINGLE EGG SPLAT)'),
    ('4다스 펀', '알 4다스', '이름 뜻으로(4 DOZEN FUN)'),
    ('버디 버디스', '새 친구들', '이름 뜻으로(BIRDY BUDDIES)'),
    ('치킨 체이스', '닭 쫓기', '이름 뜻으로(CHICKEN CHASE)'),
    ('에그 어 플렌티', '알 듬뿍', '이름 뜻으로(EGGS A PLENTY)'),
    ('핫 앤 콜드', '불과 얼음', '이름 뜻으로(HOT N\' COLD)'),
    ('스니키', '살금살금', '이름 뜻으로(SNEAKY)'),
    ('빅 뱅', '대폭발', '이름 뜻으로(BIG BANGS)'),
    # 013 통독에서
    ('선라이트', '햇빛', '주문 이름 통일(SUNLIGHT=햇빛)'),
    ('라이프 포스', '생명력', '주문 이름 통일(LIFE FORCE=생명력)'),
    ('해초의 성역', '해초 성소', '지명 통일(SEAWEED SANCTUM=해초 성소)'),
    ('물고기 신전', '물고기 사원', '지명 통일(TEMPLE OF THE FISHES=물고기 사원)'),
    ('직원 숙소', '일꾼 숙소', '용어 통일(WORKERS\' QUARTERS=일꾼 숙소)'),
    ('공장 직원', '공장 일꾼', '용어 통일(FACTORY WORKERS=공장 일꾼)'),
    ('서비스 엘리베이터', '업무용 엘리베이터', '용어 통일(SERVICE ELEVATOR)'),
    ('엘리베이터 샤프트', '승강기 통로', '용어 통일(LIFT/ELEVATOR SHAFT=승강기 통로)'),
    ('케이블 룸', '케이블실', '지명 통일(CABLE ROOM=케이블실)'),
    # 014 통독에서
    ('로저의 호수', '로저의 석호', '지명 통일(JOLLY ROGER\'S LAGOON=졸리 로저의 석호)'),
    ('팁턴', '팁텁', '이름 통일(TIPTUP=팁텁)'),
    ('수상 바이크', '웨이브레이서', '이름 통일(WAVERACER=웨이브레이서)'),
    ('잼자의', '잼자스의', '이름 통일(JAMJARS=잼자스)'),
    ('보기 베어', '보기 곰', '이름(BOGGY BEAR)'),
    ('반조 베어', '반조 곰', '이름(BANJO BEAR)'),
    ('암호 방', '코드의 방', '지명 통일(CODE ROOM/CHAMBER=코드의 방)'),
    ('타깃잔의 신전', '타깃잔의 사원', '지명 통일(TARGITZAN\'S TEMPLE=타깃잔의 사원)'),
    ('닷지 돔', '범퍼카 돔', '이름 통일(DODGEM=범퍼카)'),
    ('닷지 게임', '범퍼카 게임', '이름 통일(DODGEM=범퍼카)'),
    ('작업자 숙소', '일꾼 숙소', '용어 통일(WORKERS\' QUARTERS=일꾼 숙소)'),
    ('록너츠', '록넛츠', '이름 통일(ROCKNUTS=록넛츠)'),
    ('스톰포노돈', '스톰포나돈', '이름 통일(STOMPONADON=스톰포나돈)'),
    ('별 스피너', '스타 스피너', '이름 통일(STAR SPINNER=스타 스피너)'),
    ('움바의 천막집', '움바의 천막', '지명 통일(WUMBA\'S WIGWAM=움바의 천막)'),
    # 015 통독에서
    ('광부', '탐광꾼', '용어 통일(PROSPECTOR=탐광꾼)', 'PROSPECTOR'),
    ('두블론', '더블룬', '용어 통일(DOUBLOONS=더블룬)'),
]


# button icons {80}..{8F} read as «X 버튼», so the josa after them takes the 받침 form
ICON_JOSA = re.compile(r'(\{8[0-9A-F]\})(를|로|와|가|는)(?![가-힣])')
ICON_CONS = {'를': '을', '로': '으로', '와': '과', '가': '이', '는': '은'}


def jong(ch):
    """받침: None(한글 아님) / 0(없음) / 8(ㄹ) / 그 밖의 번호."""
    o = ord(ch) - 0xAC00
    return (o % 28) if 0 <= o < 11172 else None


JOSA = [('이에요', '예요'), ('이야', '야'), ('이랑', '랑'), ('이나', '나'), ('으로', '로'),
        ('은', '는'), ('을', '를'), ('과', '와'), ('이', '가')]
_JOSA_RE = '|'.join(sorted({x for pair in JOSA for x in pair}, key=len, reverse=True))


def fit_josa(word, josa):
    j = jong(word[-1])
    if j is None:
        return josa
    for cons, vow in JOSA:
        if josa in (cons, vow):
            if cons == '으로':
                return '로' if j in (0, 8) else '으로'
            return vow if j == 0 else cons
    return josa


def replace_term(t, a, b):
    """a→b, 바로 뒤 조사를 b 받침에 맞춘다. «이/가·이야»는 뒤가 한글이면 조사로 보지 않는다."""
    pat = a[3:] if a.startswith('re:') else re.escape(a)

    def sub(m):
        jo = m.group(1)
        if jo is None:
            return b
        if jo in ('이', '가', '이야', '야') and m.group(2) and jong(m.group(2)) is not None:
            return b + jo
        return b + fit_josa(b, jo)
    return re.sub('(?:' + pat + ')(' + _JOSA_RE + ')?(?=(.?))', sub, t)


def has(t, a):
    return re.search(a[3:], t) if a.startswith('re:') else a in t


def main():
    fixes = {}
    if os.path.exists(FIXES):
        for ln in open(FIXES, encoding='utf-8-sig').read().splitlines()[1:]:
            if ln.strip():
                loc, new, why = ln.split('\t')
                assert loc not in fixes, 'duplicate fix ' + loc
                fixes[loc] = (new, why)
    unify = {}
    if os.path.exists(UNIFY) and '--no-unify' not in sys.argv:
        for ln in open(UNIFY, encoding='utf-8-sig').read().splitlines()[1:]:
            if ln.strip():
                loc, new, why = ln.split('	')
                unify[loc] = (new, why)
    os.makedirs(OUT, exist_ok=True)
    log = ['위치\tID\t원문\t수정 전\t수정 후\t이유']
    seen = set()
    for f in sorted(glob.glob(os.path.join(SRC, '*.tsv'))):
        lines = open(f, encoding='utf-8-sig').read().splitlines()
        out = [lines[0]]
        for ln in lines[1:]:
            c = ln.split('\t')
            if len(c) > 5 and c[5]:
                before = c[5]
                t, why = before, []
                if c[1] in fixes:      # row fix first, so later glossary entries reach fixed rows too
                    t, r = fixes[c[1]]
                    why.append(r)
                    seen.add(c[1])
                for g in GLOSSARY:
                    a, b, r = g[:3]
                    if (len(g) < 4 or g[3] in c[4]) and has(t, a):
                        t = replace_term(t, a, b)
                        why.append(r)
                t2 = ICON_JOSA.sub(lambda m: m.group(1) + ICON_CONS[m.group(2)], t)
                if t2 != t:
                    t = t2
                    why.append('버튼 아이콘 뒤 조사 통일(«버튼»으로 읽어 을·으로·과)')
                if c[1] in unify:
                    t, r = unify[c[1]]
                    why.append(r)
                if t != before:
                    c[5] = t
                    log.append('\t'.join((c[1], c[0], c[4], before, t, ' / '.join(dict.fromkeys(why)))))
            out.append('\t'.join(c))
        open(os.path.join(OUT, os.path.basename(f)), 'w', encoding='utf-8', newline='\n').write('\n'.join(out) + '\n')
    missing = set(fixes) - seen
    assert not missing, 'fixes for unknown rows: %s' % sorted(missing)
    open(LOG, 'w', encoding='utf-8', newline='\n').write('\n'.join(log) + '\n')
    print('changed rows', len(log) - 1, '->', OUT)


if __name__ == '__main__':
    main()
