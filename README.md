# 智慧问学系统

* 问学：通过向大模型提问，并依据回复内容理解学习的以问促学过程。

* 智慧问学系统：提升学生向大模型的提问能力，以及判别大模型回复的能力。

本系统使用SSM框架实现，使用Spring AI调用大语言模型。使用MySQL数据库存储数据。

## 使用说明

1. 配置API密钥
   在项目根下创建.env文件，其中输入，获取看参考：
     ```
	 X-Api-App-ID=YOURS
	 X-Api-Access-Key=YOURS
	 ```
API-access-key获取可参考
1. https://www.volcengine.com/docs/6561/1594356
2. https://blog.csdn.net/crazyjinks/article/details/147424604

2. 
   ```bash
   pip install -r requirements.txt
   
3. 项目分两个版本：
* 本地无界面的在local目录下，启动命令：
```
python main.py
```
* Web界面（FastAPI）的在web目录下，运行无反应出错
