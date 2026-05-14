#!/usr/bin/env python3
import argparse
import json
import ssl
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / 'gh-pages'
INDEX_PATH = PAGES / 'data' / 'bottles.index.json'
DETAIL_DIR = PAGES / 'data' / 'bottles'
MIN_CONFIDENCE = 0.5
WEIGHTS = {
    'brandConfidence': 0.30,
    'productConfidence': 0.35,
    'variantConfidence': 0.20,
    'imageMatchConfidence': 0.15,
}
ALLOWED_IMAGE_SOURCES = {
    'official',
    'official-alternative',
    'retailer',
    'review',
    'reference',
    'placeholder',
}
REQUIRED_INDEX_FIELDS = {
    'id',
    'name',
    'subtitle',
    'category',
    'region',
    'image',
    'flavors',
    'identificationConfidence',
    'imageSource',
    'imageSourceUrl',
}
REQUIRED_DETAIL_FIELDS = {
    'id',
    'name',
    'subtitle',
    'category',
    'region',
    'abv',
    'age',
    'flavors',
    'description',
    'notes',
    'identificationConfidence',
    'image',
    'imageSource',
    'imageSourceUrl',
    'identification',
    'hookMessage',
}
REQUIRED_IDENTIFICATION_FIELDS = {
    'status',
    'confidence',
    'confidenceMethod',
    'brandConfidence',
    'productConfidence',
    'variantConfidence',
    'imageMatchConfidence',
    'evidence',
    'issues',
}
FORBIDDEN_DESCRIPTION_PHRASES = [
    '상단',
    '중단',
    '하단',
    '선반',
    '이미지에서',
    '라벨이 확인',
    '라벨로 확인',
    '표기가 확인',
    '읽히는',
    '기록했습니다',
]


def fail(errors, message):
    errors.append(message)


def load_json(path, errors):
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        fail(errors, f'JSON을 읽을 수 없습니다: {path}: {exc}')
        return None


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def expected_confidence(identification):
    return round(sum(identification[key] * weight for key, weight in WEIGHTS.items()), 2)


def validate_confidence(bottle_id, identification, top_level_confidence, errors):
    missing = REQUIRED_IDENTIFICATION_FIELDS - set(identification)
    if missing:
        fail(errors, f'{bottle_id}: identification 필드 누락: {sorted(missing)}')
        return

    for key in WEIGHTS:
        value = identification[key]
        if not is_number(value) or not 0 <= value <= 1:
            fail(errors, f'{bottle_id}: {key}는 0~1 숫자여야 합니다: {value!r}')

    confidence = identification['confidence']
    if not is_number(confidence) or not 0 <= confidence <= 1:
        fail(errors, f'{bottle_id}: identification.confidence는 0~1 숫자여야 합니다: {confidence!r}')
        return

    if not is_number(top_level_confidence):
        fail(errors, f'{bottle_id}: identificationConfidence는 숫자여야 합니다: {top_level_confidence!r}')
        return

    expected = expected_confidence(identification)
    if abs(confidence - expected) > 0.01:
        fail(errors, f'{bottle_id}: confidence 계산 불일치: actual={confidence}, expected={expected}')

    if abs(top_level_confidence - confidence) > 0.001:
        fail(errors, f'{bottle_id}: identificationConfidence와 identification.confidence가 다릅니다: {top_level_confidence} != {confidence}')

    if identification['confidenceMethod'] != 'weighted-average-v1':
        fail(errors, f'{bottle_id}: confidenceMethod가 올바르지 않습니다: {identification["confidenceMethod"]!r}')



def validate_image(bottle_id, image, image_source, image_source_url, identification, errors):
    if image_source not in ALLOWED_IMAGE_SOURCES:
        fail(errors, f'{bottle_id}: imageSource 허용값이 아닙니다: {image_source!r}')

    if image_source == 'placeholder':
        image_path = PAGES / image
        if not image_path.exists():
            fail(errors, f'{bottle_id}: placeholder 이미지 파일이 없습니다: {image}')
        if identification.get('imageMatchConfidence', 1) > 0.1:
            fail(errors, f'{bottle_id}: placeholder는 imageMatchConfidence <= 0.1 이어야 합니다.')
        return

    if not image.startswith('http'):
        image_path = PAGES / image
        if not image_path.exists():
            fail(errors, f'{bottle_id}: 로컬 이미지 파일이 없습니다: {image}')

    if not image_source_url:
        fail(errors, f'{bottle_id}: imageSourceUrl이 비어 있습니다.')

    if image_source == 'official-alternative' and identification.get('imageMatchConfidence', 1) > 0.5:
        fail(errors, f'{bottle_id}: official-alternative는 imageMatchConfidence를 보수적으로 낮게 유지해야 합니다.')



def validate_description(bottle_id, description, errors):
    for phrase in FORBIDDEN_DESCRIPTION_PHRASES:
        if phrase in description:
            fail(errors, f'{bottle_id}: 공개 description에 식별 과정 문구가 있습니다: {phrase}')



def validate_html(errors):
    index_html = (PAGES / 'index.html').read_text()
    detail_html = (PAGES / 'detail.html').read_text()

    if 'MIN_CONFIDENCE = 0.5' not in index_html:
        fail(errors, 'index.html에 MIN_CONFIDENCE = 0.5 필터가 없습니다.')
    if 'MIN_CONFIDENCE = 0.5' not in detail_html:
        fail(errors, 'detail.html에 MIN_CONFIDENCE = 0.5 필터가 없습니다.')
    if 'shareButton.addEventListener' not in detail_html:
        fail(errors, 'detail.html에 share 버튼 핸들러가 없습니다.')
    if '<blockquote id="hook-message"' not in detail_html:
        fail(errors, 'detail.html에 hookMessage blockquote가 없습니다.')



def check_external_images(index):
    context = ssl._create_unverified_context()
    headers = {'User-Agent': 'Mozilla/5.0 addictive-data-validator/1.0'}
    items = [(item['id'], item['image']) for item in index if item['image'].startswith('http')]

    def check(item):
        bottle_id, url = item
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=20, context=context) as response:
                response.read(256)
                content_type = response.headers.get('content-type', '')
                ok = response.status == 200 and 'image' in content_type.lower()
                return bottle_id, ok, response.status, content_type, ''
        except Exception as exc:
            return bottle_id, False, None, '', str(exc)[:200]

    errors = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(check, item) for item in items]
        for future in as_completed(futures):
            bottle_id, ok, status, content_type, error = future.result()
            if not ok:
                errors.append(f'{bottle_id}: 외부 이미지 접근 실패: status={status}, content-type={content_type}, error={error}')
    return errors


def main():
    parser = argparse.ArgumentParser(description='보틀 데이터 검증')
    parser.add_argument('--check-images', action='store_true', help='외부 이미지 URL 접근까지 검증합니다.')
    args = parser.parse_args()

    errors = []
    index = load_json(INDEX_PATH, errors)
    if index is None:
        print('\n'.join(errors), file=sys.stderr)
        return 1

    if not isinstance(index, list):
        fail(errors, 'bottles.index.json은 배열이어야 합니다.')
        index = []

    ids = [item.get('id') for item in index if isinstance(item, dict)]
    duplicate_ids = sorted({bottle_id for bottle_id in ids if ids.count(bottle_id) > 1})
    if duplicate_ids:
        fail(errors, f'중복 id가 있습니다: {duplicate_ids}')

    for item in index:
        bottle_id = item.get('id', '<unknown>')
        missing = REQUIRED_INDEX_FIELDS - set(item)
        if missing:
            fail(errors, f'{bottle_id}: index 필드 누락: {sorted(missing)}')
            continue

        detail_path = DETAIL_DIR / f'{bottle_id}.json'
        if not detail_path.exists():
            fail(errors, f'{bottle_id}: 상세 JSON 파일이 없습니다: {detail_path}')
            continue

        detail = load_json(detail_path, errors)
        if detail is None:
            continue

        missing_detail = REQUIRED_DETAIL_FIELDS - set(detail)
        if missing_detail:
            fail(errors, f'{bottle_id}: 상세 필드 누락: {sorted(missing_detail)}')
            continue

        if detail['id'] != bottle_id:
            fail(errors, f'{bottle_id}: 상세 id가 파일/index와 다릅니다: {detail["id"]}')

        for key in ['name', 'subtitle', 'category', 'region', 'image', 'imageSource', 'imageSourceUrl']:
            if item[key] != detail[key]:
                fail(errors, f'{bottle_id}: index와 상세의 {key} 값이 다릅니다.')

        if not isinstance(item['flavors'], list) or not item['flavors']:
            fail(errors, f'{bottle_id}: flavors는 비어 있지 않은 배열이어야 합니다.')

        notes = detail['notes']
        if not isinstance(notes, dict) or not {'nose', 'palate', 'finish'} <= set(notes):
            fail(errors, f'{bottle_id}: notes에는 nose/palate/finish가 필요합니다.')

        if not detail['description']:
            fail(errors, f'{bottle_id}: description이 비어 있습니다.')
        else:
            validate_description(bottle_id, detail['description'], errors)

        if not detail['hookMessage']:
            fail(errors, f'{bottle_id}: hookMessage가 비어 있습니다.')

        validate_confidence(bottle_id, detail['identification'], detail['identificationConfidence'], errors)
        if item['identificationConfidence'] != detail['identificationConfidence']:
            fail(errors, f'{bottle_id}: index와 상세의 identificationConfidence가 다릅니다.')

        validate_image(
            bottle_id,
            detail['image'],
            detail['imageSource'],
            detail['imageSourceUrl'],
            detail['identification'],
            errors,
        )

    detail_ids = {path.stem for path in DETAIL_DIR.glob('*.json')}
    index_ids = set(ids)
    orphan_details = sorted(detail_ids - index_ids)
    if orphan_details:
        fail(errors, f'index에 없는 상세 JSON이 있습니다: {orphan_details}')

    validate_html(errors)

    if args.check_images:
        errors.extend(check_external_images(index))

    visible_count = sum(1 for item in index if item.get('identificationConfidence', 0) >= MIN_CONFIDENCE)
    hidden_count = len(index) - visible_count

    if errors:
        print('검증 실패')
        for error in errors:
            print(f'- {error}')
        return 1

    print('검증 성공')
    print(f'- 전체 보틀: {len(index)}')
    print(f'- 노출 보틀(confidence >= {MIN_CONFIDENCE}): {visible_count}')
    print(f'- 숨김 보틀(confidence < {MIN_CONFIDENCE}): {hidden_count}')
    if args.check_images:
        print('- 외부 이미지 URL 확인 완료')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
