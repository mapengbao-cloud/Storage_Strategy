import json, os, pymysql
conn = pymysql.connect(host="rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com", port=3306, user="pengyiqiang", password="pengyiqiang123", database="tianrun_new", charset="utf8mb4", connect_timeout=10, read_timeout=30)
cur = conn.cursor()
