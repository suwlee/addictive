# 보틀 데이터 업데이트 지침

이 문서는 `addictive` GitHub Pages 데모의 보틀 데이터를 업데이트할 때 사용하는 작업 지침과 프롬프트입니다.

## 배포 데이터 위치

```text
gh-pages/
  index.html
  detail.html
  data/
    bottles.index.json
    bottles/*.json
  assets/
    bottles/placeholder.svg
```

## 데이터 업데이트 프롬프트

아래 프롬프트를 새 보틀 사진/데이터 업데이트 작업에 사용합니다.

```text
소스 이미지에서 보틀 후보를 추출해서 gh-pages/data/bottles.index.json 및 gh-pages/data/bottles/*.json을 업데이트해줘.

규칙:
- 제공 이미지 crop 이미지는 사용하지 말 것.
- 공식 홈페이지/브랜드 CDN/press kit 이미지를 최우선으로 사용할 것.
- 공식 동일 제품 이미지를 못 찾았지만 텍스트/라벨 confidence가 높으면 이미지 검색을 사용해 대체 이미지를 찾을 것.
- 텍스트/라벨 confidence가 높은 기준은 대략 brandConfidence >= 0.8 이고 productConfidence >= 0.65 인 경우로 본다.
- 이미지 검색 결과는 아무 이미지나 쓰지 말고 아래 우선순위로 선택할 것.
  1. 공식 사이트의 동일 제품 이미지: imageSource = official
  2. 공식 사이트의 같은 브랜드/라인 대체 이미지: imageSource = official-alternative
  3. 리테일러 제품 이미지: imageSource = retailer
  4. 리뷰/미디어 이미지: imageSource = review
  5. 기타 신뢰 가능한 참조 이미지: imageSource = reference
- 공식 대체 이미지나 리테일러/리뷰 이미지를 쓰는 경우, 동일 제품 이미지가 아닐 수 있음을 identification.issues에 명시할 것.
- 이미지 출처 URL을 반드시 imageSourceUrl에 기록할 것.
- 이미지가 동일 제품이 아니면 imageMatchConfidence를 낮게 유지하고 identification.issues에 명시할 것.
- 동일/대체 이미지를 모두 못 찾거나 텍스트/라벨 confidence가 낮으면 assets/bottles/placeholder.svg를 사용할 것.
- confidence는 세부 confidence의 가중 평균으로 계산할 것.
  - brandConfidence: 0.30
  - productConfidence: 0.35
  - variantConfidence: 0.20
  - imageMatchConfidence: 0.15
- identificationConfidence와 identification.confidence는 같은 숫자여야 한다.
- confidence >= 0.5만 목록/상세에서 노출되도록 유지할 것.
- 브로셔 description에는 식별 과정 문구를 쓰지 말 것.
  - 금지 예: 이미지에서 확인, 상단/중단/하단 선반, 라벨이 확인, 라벨로 확인, 표기가 확인, 읽히는, 기록했습니다.
- 식별 근거는 identification.evidence/issues에만 기록할 것.
- hookMessage를 각 보틀별로 짧고 광고성 있게 작성할 것.
- 데이터 수정 후 python3 tools/validate-data.py를 실행해서 검증할 것.
- 외부 이미지 URL까지 확인해야 하면 python3 tools/validate-data.py --check-images를 실행할 것.
```

## confidence 기준

`identification.confidence`는 아래 세부 점수의 가중 평균입니다.

```text
confidence =
  brandConfidence * 0.30 +
  productConfidence * 0.35 +
  variantConfidence * 0.20 +
  imageMatchConfidence * 0.15
```

| 점수 | 의미 |
|---:|---|
| 0.95 ~ 1.00 | 제품명, 라인업, 연식/도수/배치까지 명확 |
| 0.80 ~ 0.94 | 제품명과 라인업은 거의 확실, 세부 스펙 일부만 불확실 |
| 0.60 ~ 0.79 | 브랜드/제품군은 확실, 세부 제품명은 후보 |
| 0.40 ~ 0.59 | 브랜드는 보이나 제품명/라인업 불확실 |
| 0.20 ~ 0.39 | 일부 단서만 있음 |
| 0.00 ~ 0.19 | 추정 수준, 공개 메뉴에 쓰기 위험 |

## imageSource 값

허용 값:

- `official`: 공식 동일 제품 이미지
- `official-alternative`: 공식 이미지이지만 동일 제품/배치가 아닌 대체 이미지
- `retailer`: 리테일러 제품 이미지
- `review`: 리뷰/미디어 이미지
- `reference`: 기타 신뢰 가능한 참조 이미지
- `placeholder`: 이미지 미확보

## 공식 이미지를 못 찾은 경우의 이미지 검색 기준

공식 동일 제품 이미지를 못 찾았더라도 텍스트/라벨 신뢰도가 높으면 이미지 검색을 통해 대체 이미지를 사용할 수 있습니다.

권장 조건:

```text
brandConfidence >= 0.8
productConfidence >= 0.65
```

이 조건을 만족하면 대체 이미지를 사용할 수 있습니다. 단, 대체 이미지가 동일 제품/배치임을 보장하지 못하면 `imageMatchConfidence`를 낮게 유지합니다.

예시:

```json
{
  "imageSource": "official-alternative",
  "imageSourceUrl": "https://cognac-peyrot.com/produit/heritage-coffret/",
  "identification": {
    "brandConfidence": 0.9,
    "productConfidence": 0.75,
    "variantConfidence": 0.55,
    "imageMatchConfidence": 0.25,
    "issues": [
      "공식 대체 이미지이며 Lot 70 동일 병입 이미지는 아닙니다."
    ]
  }
}
```

텍스트/라벨 confidence가 낮거나 대체 이미지가 오해를 만들 가능성이 크면 `placeholder`를 유지합니다.

## 브로셔 문구 원칙

공개용 `description`은 제품 소개만 작성합니다.

좋은 예:

```text
Knob Creek 9 Year는 100 proof, 9년 숙성 버번으로 진한 오크와 바닐라, 견과류 캐릭터가 특징입니다.
```

나쁜 예:

```text
하단 중앙 우측의 Knob Creek 9 라벨이 확인됩니다.
```

## 검증 명령

```bash
python3 tools/validate-data.py
python3 tools/validate-data.py --check-images
```
