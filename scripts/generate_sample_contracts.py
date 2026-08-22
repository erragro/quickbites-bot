"""
Generate three sample contract PNG images for the Contract Reader demo:
  Swiggy (Hindi) · Ola (Tamil) · Urban Company (Bengali)

Renders each contract text onto a white 850x1200 canvas using the
matching Indic font that ships with macOS. Saves as PNG so the OCR
step exercises Gemini vision multimodal — the demo-authentic path a
real gig worker would take (photograph a paper contract from their
phone).

Output goes to the scratchpad so it's ephemeral; the actual demo
seeding for a specific user uses upload_samples_to_user.py.

Usage:
    .venv/bin/python scripts/generate_sample_contracts.py \\
        --out /tmp/samples

Uploads happen separately via curl or upload_samples_to_user.py so
this script has no auth surface.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Contract corpus (verbatim in each language)
#
# Content is a compressed but realistic rendition of a real aggregator's
# T&Cs — clause structure mirrors what workers actually sign. Translations
# were prepared by hand-checking against Swiggy/Ola/Urban Company's public
# partner agreements to avoid loanword artifacts.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SampleContract:
    slug: str
    title: str
    body: str
    font_path: str


CONTRACTS = [
    SampleContract(
        slug="swiggy_partner_agreement_hi",
        title="स्विगी डिलीवरी पार्टनर अनुबंध",
        body=(
            "यह अनुबंध बंडल टेक्नोलॉजीज़ प्राइवेट लिमिटेड (कंपनी) और\n"
            "डिलीवरी पार्टनर के बीच किया गया है।\n\n"
            "1. संबंध की प्रकृति\n"
            "1.1 डिलीवरी पार्टनर स्वतंत्र ठेकेदार है, कंपनी का कर्मचारी\n"
            "नहीं है। कोई भी कर्मचारी-नियोक्ता संबंध नहीं बनता।\n\n"
            "2. सेवाएं\n"
            "2.1 डिलीवरी पार्टनर स्विगी प्लेटफ़ॉर्म के माध्यम से सौंपे गए\n"
            "आदेशों को स्वीकार करने और पूरा करने के लिए सहमत है।\n"
            "2.2 डिलीवरी पार्टनर अपने वाहन का उपयोग करेगा और ईंधन,\n"
            "रखरखाव तथा बीमा सहित सभी संबंधित खर्च वहन करेगा।\n\n"
            "3. भुगतान\n"
            "3.1 कंपनी प्लेटफ़ॉर्म पर प्रकाशित प्रति-आदेश दरों के अनुसार\n"
            "भुगतान करेगी। कंपनी अपने विवेक से किसी भी समय इन दरों को\n"
            "संशोधित कर सकती है।\n"
            "3.2 भुगतान साप्ताहिक बैंक हस्तांतरण द्वारा किया जाएगा,\n"
            "किसी भी शुल्क या दंड की कटौती के अधीन।\n\n"
            "4. समाप्ति\n"
            "4.1 दोनों पक्ष 24 घंटे का लिखित नोटिस देकर इस अनुबंध को\n"
            "समाप्त कर सकते हैं।\n"
            "4.2 कंपनी नीति उल्लंघन, ग्राहक शिकायतों या धोखाधड़ी की\n"
            "स्थिति में बिना नोटिस के डिलीवरी पार्टनर को निष्क्रिय\n"
            "कर सकती है।\n\n"
            "5. क्षतिपूर्ति\n"
            "5.1 डिलीवरी पार्टनर इस अनुबंध के तहत सेवाओं के प्रदर्शन से\n"
            "उत्पन्न किसी भी दावे से कंपनी को हानिरहित रखेगा।\n"
        ),
        font_path="/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
    ),
    SampleContract(
        slug="ola_driver_agreement_ta",
        title="ஓலா ஓட்டுநர் ஒப்பந்தம்",
        body=(
            "இந்த ஒப்பந்தம் ஏஎன்ஐ டெக்னாலஜிஸ் பிரைவேட் லிமிடெட்\n"
            "(நிறுவனம்) மற்றும் ஓட்டுநர் பங்குதாரர் இடையே செய்யப்பட்டது.\n\n"
            "1. உறவின் தன்மை\n"
            "1.1 ஓட்டுநர் ஒரு சுதந்திரமான ஒப்பந்தக்காரர், நிறுவனத்தின்\n"
            "ஊழியர் அல்ல. வேலைவாய்ப்பு உறவு ஏதும் உருவாகாது.\n\n"
            "2. சேவைகள்\n"
            "2.1 ஓட்டுநர் ஓலா தளத்தின் மூலம் ஒதுக்கப்படும் பயணங்களை\n"
            "ஏற்று நிறைவேற்றுவார்.\n"
            "2.2 ஓட்டுநர் தமது சொந்த வாகனத்தை பயன்படுத்துவார் மற்றும்\n"
            "எரிபொருள், பராமரிப்பு, காப்பீடு உள்ளிட்ட அனைத்து செலவுகளையும்\n"
            "தானே ஏற்பார்.\n\n"
            "3. பணம் செலுத்துதல்\n"
            "3.1 தளத்தில் வெளியிடப்பட்ட ஒரு பயணத்திற்கான கட்டணங்களின்\n"
            "படி நிறுவனம் பணம் செலுத்தும். இக்கட்டணங்களை நிறுவனம்\n"
            "தன் விருப்பப்படி எப்போது வேண்டுமானாலும் மாற்றலாம்.\n"
            "3.2 பணம் வாராந்திர வங்கி பரிமாற்றம் மூலம் செலுத்தப்படும்,\n"
            "ஏதேனும் கட்டணங்கள் அல்லது அபராதங்கள் கழிக்கப்பட்ட பின்.\n\n"
            "4. நிறுத்தம்\n"
            "4.1 இருதரப்பும் 24 மணிநேர எழுத்துப்பூர்வ அறிவிப்பு அளித்து\n"
            "இந்த ஒப்பந்தத்தை முடிக்கலாம்.\n"
            "4.2 கொள்கை மீறல், வாடிக்கையாளர் புகார்கள் அல்லது மோசடி\n"
            "நிகழ்வுகளில் நிறுவனம் ஓட்டுநரை அறிவிப்பின்றி முடக்கலாம்.\n\n"
            "5. இழப்பீடு\n"
            "5.1 இந்த ஒப்பந்தத்தின் கீழ் சேவைகளை வழங்குவதிலிருந்து\n"
            "எழும் எந்த கோரிக்கையிலிருந்தும் ஓட்டுநர் நிறுவனத்தை\n"
            "பாதுகாப்பார்.\n"
        ),
        font_path="/System/Library/Fonts/Supplemental/Tamil Sangam MN.ttc",
    ),
    SampleContract(
        slug="urbancompany_partner_agreement_bn",
        title="আরবান কোম্পানি পার্টনার চুক্তি",
        body=(
            "এই চুক্তি আরবান কোম্পানি (নিয়োগকারী) এবং সেবা পার্টনারের\n"
            "মধ্যে সম্পাদিত হয়েছে।\n\n"
            "১. সম্পর্কের প্রকৃতি\n"
            "১.১ সেবা পার্টনার একজন স্বাধীন ঠিকাদার, কোম্পানির কর্মচারী\n"
            "নন। এই চুক্তিতে কোনো কর্মচারী-নিয়োগকারী সম্পর্ক তৈরি হয় না।\n\n"
            "২. পরিষেবা\n"
            "২.১ সেবা পার্টনার আরবান কোম্পানি অ্যাপের মাধ্যমে বরাদ্দকৃত\n"
            "কাজগুলি গ্রহণ ও সম্পন্ন করবেন।\n"
            "২.২ সেবা পার্টনার তাঁর নিজের সরঞ্জাম ব্যবহার করবেন এবং\n"
            "যাতায়াত ও প্রয়োজনীয় সমস্ত খরচ বহন করবেন।\n\n"
            "৩. পারিশ্রমিক\n"
            "৩.১ প্ল্যাটফর্মে প্রকাশিত হারের ভিত্তিতে কোম্পানি পারিশ্রমিক\n"
            "প্রদান করবে। কোম্পানি যেকোনো সময় নিজের বিবেচনায় এই হার\n"
            "পরিবর্তন করতে পারবে।\n"
            "৩.২ পারিশ্রমিক সাপ্তাহিক ব্যাঙ্ক হস্তান্তরের মাধ্যমে দেওয়া হবে,\n"
            "প্রযোজ্য শুল্ক ও জরিমানা কেটে নেওয়ার পর।\n\n"
            "৪. সমাপ্তি\n"
            "৪.১ উভয় পক্ষ ২৪ ঘণ্টার লিখিত নোটিশে এই চুক্তি বাতিল\n"
            "করতে পারবে।\n"
            "৪.২ নীতি লঙ্ঘন, গ্রাহকের অভিযোগ বা প্রতারণামূলক কর্মকাণ্ডের\n"
            "ক্ষেত্রে কোম্পানি বিনা নোটিশে পার্টনারকে নিষ্ক্রিয় করতে পারে।\n\n"
            "৫. ক্ষতিপূরণ\n"
            "৫.১ এই চুক্তির অধীনে পরিষেবা প্রদানের ফলে উদ্ভূত যেকোনো\n"
            "দাবি থেকে সেবা পার্টনার কোম্পানিকে ক্ষতিপূরণ দেবেন।\n"
        ),
        # Kohinoor Bangla ships in /System/Library/Fonts/ and handles the
        # full ligature set cleanly; Bangla Sangam MN raises "invalid
        # argument" on some glyph sequences in PIL's default text engine.
        font_path="/System/Library/Fonts/KohinoorBangla.ttc",
    ),
]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


CANVAS_W = 850
CANVAS_H = 1250
MARGIN = 50
TITLE_SIZE = 24
BODY_SIZE = 16
LINE_SPACING = 10  # pixels between lines
BG = (255, 255, 255)
FG = (17, 17, 17)


def render(sample: SampleContract, out_dir: Path) -> Path:
    """Render one contract to a PNG. Returns the output path."""
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(sample.font_path, TITLE_SIZE)
    body_font = ImageFont.truetype(sample.font_path, BODY_SIZE)

    y = MARGIN
    draw.text((MARGIN, y), sample.title, font=title_font, fill=FG)
    # Title takes ~1.5 lines; move down.
    y += TITLE_SIZE + LINE_SPACING * 2

    # Horizontal rule under the title.
    draw.line([(MARGIN, y), (CANVAS_W - MARGIN, y)], fill=(200, 200, 200), width=1)
    y += LINE_SPACING * 2

    for line in sample.body.splitlines():
        draw.text((MARGIN, y), line, font=body_font, fill=FG)
        y += BODY_SIZE + LINE_SPACING
        if y > CANVAS_H - MARGIN:
            break  # ran out of canvas; contract will be truncated

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sample.slug}.png"
    img.save(out_path, "PNG", optimize=True)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="/private/tmp/sreshtha-samples",
        help="Directory to write the PNGs into.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    for sample in CONTRACTS:
        path = render(sample, out_dir)
        size_kb = path.stat().st_size // 1024
        print(f"  {sample.slug}: {path} ({size_kb} KB)")


if __name__ == "__main__":
    main()
