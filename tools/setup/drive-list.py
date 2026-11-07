import codecs,json,re,sys,urllib.request
url='https://drive.google.com/drive/folders/'+sys.argv[1]
html=urllib.request.urlopen(url).read().decode()
match=re.search(r"window\['_DRIVE_ivd'\] = '([^']*)'",html)
if not match: raise SystemExit('No listing data')
value=match[1]
for _ in range(3):
    if value.startswith('['):break
    value=codecs.decode(value,'unicode_escape')
data=json.loads(value)
for row in data[0]: print(row[0],row[2],row[3],row[13] if len(row)>13 else '')
