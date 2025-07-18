# RealtimeDialog

实时语音对话程序，支持语音输入和语音输出。

## 使用说明

此demo使用python3.7环境进行开发调试，其他python版本可能会有兼容性问题，需要自己尝试解决。

1. 配置API密钥
   在项目根下创建.env文件，其中输入，获取看参考：
     ```
	 X-Api-App-ID=YOURS
	 X-Api-Access-Key=YOURS
	 ```
API-access-key获取可参考
1. https://www.volcengine.com/docs/6561/1594356
2. https://blog.csdn.net/crazyjinks/article/details/147424604

2. 安装依赖
   ```bash
   pip install -r requirements.txt
   
3. 项目分两个版本：
* 本地无界面的在local目录下，启动命令：
```
python main.py
```
* Web界面（FastAPI）的在web目录下，运行无反应出错
