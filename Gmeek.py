# -*- coding: utf-8 -*-
import os
import re
import json
import time
import datetime
import shutil
import urllib.parse
import xml.etree.ElementTree as ET
import requests
import argparse
import html
import markdown # [新增] 引入本地渲染库，替代 GitHub API
from github import Github, Auth
from xpinyin import Pinyin
from feedgen.feed import FeedGenerator
from jinja2 import Environment, FileSystemLoader
from transliterate import translit
from collections import OrderedDict

# --- Constants (No changes) ---
i18n={"Search":"Search","switchTheme":"switch theme","home":"home","comments":"comments","run":"run ","days":" days","Previous":"Previous","Next":"Next"}
i18nCN={"Search":"搜索","switchTheme":"切换主题","home":"首页","comments":"评论","run":"网站运行","days":"天","Previous":"上一页","Next":"下一页"}
i18nRU={"Search":"Поиск","switchTheme": "Сменить тему","home":"Главная","comments":"Комментарии","run":"работает ","days":" дней","Previous":"Предыдущая","Next":"Следующая"}
IconBase={
    "post":"M0 3.75C0 2.784.784 2 1.75 2h12.5c.966 0 1.75.784 1.75 1.75v8.5A1.75 1.75 0 0 1 14.25 14H1.75A1.75 1.75 0 0 1 0 12.25Zm1.75-.25a.25.25 0 0 0-.25.25v8.5c0 .138.112.25.25.25h12.5a.25.25 0 0 0 .25-.25v-8.5a.25.25 0 0 0-.25-.25ZM3.5 6.25a.75.75 0 0 1 .75-.75h7a.75.75 0 0 1 0 1.5h-7a.75.75 0 0 1-.75-.75Zm.75 2.25h4a.75.75 0 0 1 0 1.5h-4a.75.75 0 0 1 0-1.5Z",
    "link":"m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z",
    "about":"M10.561 8.073a6.005 6.005 0 0 1 3.432 5.142.75.75 0 1 1-1.498.07 4.5 4.5 0 0 0-8.99 0 .75.75 0 0 1-1.498-.07 6.004 6.004 0 0 1 3.431-5.142 3.999 3.999 0 1 1 5.123 0ZM10.5 5a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z",
    "sun":"M8 10.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM8 12a4 4 0 100-8 4 4 0 000 8zM8 0a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0V.75A.75.75 0 018 0zm0 13a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 018 13zM2.343 2.343a.75.75 0 011.061 0l1.06 1.061a.75.75 0 01-1.06 1.06l-1.06-1.06a.75.75 0 010-1.06zm9.193 9.193a.75.75 0 011.06 0l1.061 1.06a.75.75 0 01-1.06 1.061l-1.061-1.06a.75.75 0 010-1.061zM16 8a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5A.75.75 0 0116 8zM3 8a.75.75 0 01-.75.75H.75a.75.75 0 010-1.5h1.5A.75.75 0 013 8zm10.657-5.657a.75.75 0 010 1.061l-1.061 1.06a.75.75 0 11-1.06-1.06l1.06-1.06a.75.75 0 011.06 0zm-9.193 9.193a.75.75 0 010 1.06l-1.06 1.061a.75.75 0 11-1.061-1.06l1.06-1.061a.75.75 0 011.061 0z",
    "moon":"M9.598 1.591a.75.75 0 01.785-.175 7 7 0 11-8.967 8.967.75.75 0 01.961-.96 5.5 5.5 0 007.046-7.046.75.75 0 01.175-.786zm1.616 1.945a7 7 0 01-7.678 7.678 5.5 5.5 0 107.678-7.678z",
    "search":"M15.7 13.3l-3.81-3.83A5.93 5.93 0 0 0 13 6c0-3.31-2.69-6-6-6S1 2.69 1 6s2.69 6 6 6c1.3 0 2.48-.41 3.47-1.11l3.83 3.81c.19.2.45.3.7.3.25 0 .52-.09.7-.3a.996.996 0 0 0 0-1.41v.01zM7 10.7c-2.59 0-4.7-2.11-4.7-4.7 0-2.59 2.11-4.7 4.7-4.7 2.59 0 4.7 2.11 4.7 4.7 0 2.59-2.11 4.7-4.7 4.7z",
    "rss":"M2.002 2.725a.75.75 0 0 1 .797-.699C8.79 2.42 13.58 7.21 13.974 13.201a.75.75 0 0 1-1.497.098 10.502 10.502 0 0 0-9.776-9.776.747.747 0 0 1-.7-.798ZM2.84 7.05h-.002a7.002 7.002 0 0 1 6.113 6.111.75.75 0 0 1-1.49.178 5.503 5.503 0 0 0-4.8-4.8.75.75 0 0 1 .179-1.489ZM2 13a1 1 0 1 1 2 0 1 1 0 0 1-2 0Z",
    "upload":"M2.75 14A1.75 1.75 0 0 1 1 12.25v-2.5a.75.75 0 0 1 1.5 0v2.5c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25v-2.5a.75.75 0 0 1 1.5 0v2.5A1.75 1.75 0 0 1 13.25 14Z M11.78 4.72a.749.749 0 1 1-1.06 1.06L8.75 3.811V9.5a.75.75 0 0 1-1.5 0V3.811L5.28 5.78a.749.749 0 1 1-1.06-1.06l3.25-3.25a.749.749 0 0 1 1.06 0l3.25 3.25Z",
    "github":"M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z",
    "home":"M6.906.664a1.749 1.749 0 0 1 2.187 0l5.25 4.2c.415.332.657.835.657 1.367v7.019A1.75 1.75 0 0 1 13.25 15h-3.5a.75.75 0 0 1-.75-.75V9H7v5.25a.75.75 0 0 1-.75.75h-3.5A1.75 1.75 0 0 1 1 13.25V6.23c0-.531.242-1.034.657-1.366l5.25-4.2Zm1.25 1.171a.25.25 0 0 0-.312 0l-5.25 4.2a.25.25 0 0 0-.094.196v7.019c0 .138.112.25.25.25H5.5V8.25a.75.75 0 0 1 .75-.75h3.5a.75.75 0 0 1 .75.75v5.25h2.75a.25.25 0 0 0 .25-.25V6.23a.25.25 0 0 0-.094-.195Z",
    "sync":"M1.705 8.005a.75.75 0 0 1 .834.656 5.5 5.5 0 0 0 9.592 2.97l-1.204-1.204a.25.25 0 0 1 .177-.427h3.646a.25.25 0 0 1 .25.25v3.646a.25.25 0 0 1-.427.177l-1.38-1.38A7.002 7.002 0 0 1 1.05 8.84a.75.75 0 0 1 .656-.834ZM8 2.5a5.487 5.487 0 0 0-4.131 1.869l1.204 1.204A.25.25 0 0 1 4.896 6H1.25A.25.25 0 0 1 1 5.75V2.104a.25.25 0 0 1 .427-.177l1.38 1.38A7.002 7.002 0 0 1 14.95 7.16a.75.75 0 0 1-1.49.178A5.5 5.5 0 0 0 8 2.5Z",
    "copy":"M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z",
    "check":"M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"
}

class GMEEK:
    def __init__(self,options):
        self.options=options

        self.root_dir='docs/'
        self.static_dir='static/'
        self.post_folder='post/'
        self.backup_dir='backup/'
        self.post_dir=self.root_dir+self.post_folder

        self.script_dir = os.path.dirname(os.path.realpath(__file__))

        auth = Auth.Token(self.options.github_token)
        user = Github(auth=auth)
        self.repo = self.get_repo(user, options.repo_name)
        self.feed = FeedGenerator()
        self.oldFeedString=''

        self.labelColorDict=json.loads('{}')
        for label in self.repo.get_labels():
            self.labelColorDict[label.name]='#'+label.color
        print(self.labelColorDict)
        self.defaultConfig()

    def syncStaticAssets(self):
        print("====== syncing static assets ======")
    # 把 static 目录下的内容直接复制到 docs 根目录
        if os.path.exists(self.static_dir):
            for item in os.listdir(self.static_dir):
                src = os.path.join(self.static_dir, item)
                dst = os.path.join(self.root_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
            print(f"Copied contents of '{self.static_dir}' to '{self.root_dir}'")

    # 检查并复制根目录下的 images 文件夹
        image_dir = 'images'
        if os.path.exists(image_dir):
            shutil.copytree(
                image_dir,
                os.path.join(self.root_dir, image_dir),
                dirs_exist_ok=True
            )
            print(f"Copied '{image_dir}' directory to '{self.root_dir}'")

    def cleanFile(self):
        workspace_path = os.environ.get('GITHUB_WORKSPACE', '.')
        if os.path.exists(os.path.join(workspace_path, self.backup_dir)):
            shutil.rmtree(os.path.join(workspace_path, self.backup_dir))
        if os.path.exists(os.path.join(workspace_path, self.root_dir)):
            shutil.rmtree(os.path.join(workspace_path, self.root_dir))
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(self.root_dir, exist_ok=True)
        os.makedirs(self.post_dir, exist_ok=True)

    def defaultConfig(self):
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        dconfig={"singlePage":[],"hiddenPage":[],"disabledPage":[],"startSite":"","filingNum":"","onePageListNum":15,"commentLabelColor":"#006b75","yearColorList":["#bc4c00", "#0969da", "#1f883d", "#A333D0"],"i18n":"CN","themeMode":"manual","dayTheme":"light","nightTheme":"dark","urlMode":"pinyin","script":"","style":"","head":"","indexScript":"","indexStyle":"","bottomText":"","showPostSource":1,"iconList":{},"UTC":8,"rssSplit":"sentence","exlink":{},"needComment":1,"allHead":"","author":"莫白来","xName":"莫白来","xHandle":"wiselyfreely","xUrl":"https://x.com/wiselyfreely","linkedinUrl":"","youtubeUrl":"","enableAds":0,"subscribeApiUrl":"","turnstileSiteKey":"","contentCategorySlugs":{"内心秩序":"nei-xin-zhi-xu","资产护航":"zi-chan-hu-hang","数字能力":"shu-zi-neng-li"},"contentCategoryAliases":{"人生修行":"内心秩序","赚钱投资":"资产护航","技术辅助":"数字能力"},"legacyCategoryRedirects":{"xiu-xing.html":"nei-xin-zhi-xu.html","tou-zi.html":"zi-chan-hu-hang.html","ai-jiao-xue.html":"shu-zi-neng-li.html"}}

        self.blogBase={**dconfig,**config}
        for legacy_label, canonical_label in self.blogBase.get("contentCategoryAliases", {}).items():
            if legacy_label in self.labelColorDict and canonical_label not in self.labelColorDict:
                self.labelColorDict[canonical_label] = self.labelColorDict[legacy_label]
        self.blogBase["postListJson"]={}
        self.blogBase["singeListJson"]={}
        self.blogBase["labelColorDict"]=self.labelColorDict

        self.blogBase.setdefault("displayTitle", self.blogBase["title"])
        self.blogBase.setdefault("faviconUrl", self.blogBase["avatarUrl"])
        self.blogBase.setdefault("ogImage", self.blogBase["avatarUrl"])
        self.blogBase.setdefault("primerCSS", "<link href='https://www.790427.xyz/css/primer-21.0.7.min.css' rel='stylesheet' />")

        if "homeUrl" not in self.blogBase or not self.blogBase["homeUrl"]:
            owner_login = self.repo.owner.login
            repo_name = self.repo.name
            if repo_name.lower() == f"{owner_login}.github.io".lower():
                self.blogBase["homeUrl"] = f"https://{repo_name}"
            else:
                self.blogBase["homeUrl"] = f"https://{owner_login}.github.io/{repo_name}"
        self.blogBase["homeUrl"] = self.blogBase["homeUrl"].rstrip('/')
        print("GitHub Pages URL:", self.blogBase["homeUrl"])

        self.i18n = {"CN": i18nCN, "RU": i18nRU}.get(self.blogBase["i18n"], i18n)
        self.TZ = datetime.timezone(datetime.timedelta(hours=self.blogBase["UTC"]))

    def getLabelSlug(self, label):
        """Keep primary category URLs stable while auxiliary tags use pinyin."""
        canonical_label = self.blogBase.get("contentCategoryAliases", {}).get(label, label)
        return self.blogBase.get("contentCategorySlugs", {}).get(canonical_label, Pinyin().get_pinyin(label))

    def normalizeLabels(self, labels):
        """Map legacy editorial labels to their current public names."""
        aliases = self.blogBase.get("contentCategoryAliases", {})
        normalized = []
        for label in labels:
            canonical_label = aliases.get(label, label)
            if canonical_label not in normalized:
                normalized.append(canonical_label)
        return normalized

    def getContentCategory(self, labels):
        """Return the single editorial category independent of GitHub label order."""
        label_names = self.normalizeLabels([label.name if hasattr(label, "name") else label for label in labels])
        for category in self.blogBase.get("contentCategorySlugs", {}):
            if category in label_names:
                return category
        return ""

    def getSinglePageLabel(self, labels):
        label_names = [label.name if hasattr(label, "name") else label for label in labels]
        page_labels = self.blogBase["singlePage"] + self.blogBase["hiddenPage"]
        return next((label for label in label_names if label in page_labels), "")

    def validateContentCategories(self):
        categories = set(self.blogBase.get("contentCategorySlugs", {}))
        invalid_posts = []
        for issue_key, post in self.blogBase["postListJson"].items():
            matches = sorted(categories.intersection(self.normalizeLabels(post.get("labels", []))))
            if len(matches) != 1:
                invalid_posts.append(f"{issue_key}: {post['postTitle']} ({', '.join(matches) or '无正式栏目'})")
        if invalid_posts:
            details = "\n".join(invalid_posts)
            raise ValueError(f"Published articles must have exactly one content category:\n{details}")

    def get_repo(self,user:Github, repo:str):
        return user.get_repo(repo)

    def markdown2html(self, mdstr):
        html_replacements = {}
        def Gmeek_html_tag_filter(match):
            nonlocal html_replacements
            text = match.group(1)
            placeholder = f""
            html_replacements[placeholder] = text
            return f"`{placeholder}`"
        mdstr = re.sub(r'`Gmeek-html(.*?)`', Gmeek_html_tag_filter, mdstr, flags=re.DOTALL)

        # [修正] 只使用最基本的扩展，避免 No module named 'pymdownx' 报错
        extensions = [
            'markdown.extensions.extra',
            'markdown.extensions.codehilite',
            'markdown.extensions.tables',
            'markdown.extensions.toc',
            'markdown.extensions.nl2br',
            'markdown.extensions.sane_lists'
        ]

        try:
            html_content = markdown.markdown(mdstr, extensions=extensions)
        except Exception as e:
            raise Exception(f"Local markdown rendering error: {e}")

        for placeholder, original_html in html_replacements.items():
            p_wrapped_placeholder = f"<p>{placeholder}</p>"
            if p_wrapped_placeholder in html_content:
                html_content = html_content.replace(p_wrapped_placeholder, original_html)
            else:
                html_content = html_content.replace(placeholder, original_html)
        return html_content

    def renderHtml(self,template_name, context, html_dir):
        templates_path = os.path.join(self.script_dir, 'templates')
        file_loader = FileSystemLoader(templates_path)
        env = Environment(loader=file_loader)
        env.filters['tojson'] = json.dumps
        template = env.get_template(template_name)
        output = template.render(**context)
        with open(html_dir, 'w', encoding='UTF-8') as f:
            f.write(output)

    def createPostHtml(self, issue_data):
        mdFileName=re.sub(r'[<>:/\\|?*\"]|[\0-\31]', '-', issue_data["postTitle"])
        md_filepath = os.path.join(self.backup_dir, f"{mdFileName}.md")
        try:
            with open(md_filepath, 'r', encoding='UTF-8') as f:
                raw_md_content = f.read()
        except FileNotFoundError:
            print(f"Warning: Markdown file not found for '{issue_data['postTitle']}'. Skipping page generation.")
            return

        render_dict = self.blogBase.copy()
        render_dict.update(issue_data)
        render_dict["postBody"] = self.markdown2html(raw_md_content)
        render_dict["canonicalUrl"] = issue_data["postUrl"]
        primary_label = issue_data.get("contentCategory") or (issue_data["labels"][0] if issue_data.get("labels") else "")
        if primary_label and primary_label not in self.blogBase["singlePage"] and primary_label not in self.blogBase["hiddenPage"]:
            render_dict["primaryLabelUrl"] = f"{self.blogBase['homeUrl']}/{self.getLabelSlug(primary_label)}.html"
        else:
            render_dict["primaryLabelUrl"] = self.blogBase["homeUrl"]

        if self.getSinglePageLabel(issue_data.get("labels", [])) in self.blogBase["singlePage"]:
            render_dict["bottomText"]=''

        if '<pre class="notranslate">' in render_dict["postBody"]:
            keys=['sun','moon','sync','home','github','copy','check']
            if '<div class="highlight' in render_dict["postBody"]:
                render_dict["highlight"]=1
            else:
                render_dict["highlight"]=2
        else:
            keys=['sun','moon','sync','home','github']
            render_dict["highlight"]=0

        postIcon=dict(zip(keys, map(IconBase.get, keys)))

        context = {
            'blogBase': render_dict,
            'i18n': self.i18n,
            'IconList': postIcon
        }
        self.renderHtml('post.html', context, issue_data["htmlDir"])
        print(f"Created page: title={issue_data['postTitle']}, file={issue_data['htmlDir']}")

    def enrichPostNavigation(self):
        current_time = int(time.time())
        posts = [
            p for p in self.blogBase["postListJson"].values()
            if p["createdAt"] <= current_time
        ]
        posts.sort(key=lambda p: p["createdAt"], reverse=True)

        def post_summary(post):
            if not post:
                return None
            return {
                "postTitle": post["postTitle"],
                "postUrl": post["postUrl"],
                "createdDate": post["createdDate"],
                "description": post.get("description", "")
            }

        for index, post in enumerate(posts):
            post["newerPost"] = post_summary(posts[index - 1]) if index > 0 else None
            post["olderPost"] = post_summary(posts[index + 1]) if index + 1 < len(posts) else None
            primary_label = post.get("contentCategory") or self.getContentCategory(post.get("labels", []))
            related = [
                p for p in posts
                if p is not post and primary_label and primary_label in p["labels"]
            ]
            post["relatedPosts"] = [post_summary(item) for item in related[:4]]

    def createPlistHtml(self):
        current_time = int(time.time())
        published_posts = {k: v for k, v in self.blogBase["postListJson"].items() if v["createdAt"] <= current_time}
        sorted_posts = dict(sorted(published_posts.items(), key=lambda x: (x[1]["top"], x[1]["createdAt"]), reverse=True))

        post_items = list(sorted_posts.values())
        post_count = len(post_items)
        page_size = self.blogBase["onePageListNum"]
        num_pages = (post_count + page_size - 1) // page_size or 1

        for page_num in range(num_pages):
            render_dict = self.blogBase.copy()
            start_index = page_num * page_size
            end_index = start_index + page_size
            paginated_posts = post_items[start_index:end_index]
            render_dict["postListJson"] = paginated_posts

            if page_num == 0:
                html_path = f"{self.root_dir}index.html"
                render_dict["canonicalUrl"] = self.blogBase['homeUrl']
                render_dict["prevUrl"] = "disabled"
            else:
                html_path = f"{self.root_dir}page{page_num + 1}.html"
                render_dict["canonicalUrl"] = f"{self.blogBase['homeUrl']}/page{page_num + 1}.html"
                render_dict["prevUrl"] = "/index.html" if page_num == 1 else f"/page{page_num}.html"

            render_dict["nextUrl"] = f"/page{page_num + 2}.html" if end_index < post_count else "disabled"

            context = {
                'blogBase': render_dict,
                'i18n': self.i18n,
                'IconList': IconBase,
                'postListJson': paginated_posts
            }
            self.renderHtml('plist.html', context, html_path)
            print(f"Created list page: {html_path}")

    def addOnePostJson(self, issue):
        postConfig = {}
        body_content = issue.body or ""

        if body_content:
            lines = body_content.splitlines()
            last_meaningful_line = next((line.strip() for line in reversed(lines) if line.strip()), "")
            if last_meaningful_line.startswith("##{") and last_meaningful_line.endswith("}"):
                try:
                    postConfig = json.loads(last_meaningful_line[2:])
                    suffix_to_remove = last_meaningful_line.strip()
                    cleaned_body = body_content.rstrip()
                    if cleaned_body.endswith(suffix_to_remove):
                        body_content = cleaned_body[:-len(suffix_to_remove)]
                except json.JSONDecodeError:
                    postConfig = {}

        if not issue.labels:
            print(f"Skipping issue #{issue.number} because it has no labels.")
            return

        issue_labels = [label.name for label in issue.labels]
        disabled_labels = set(self.blogBase.get("disabledPage", []))
        if disabled_labels.intersection(issue_labels):
            print(f"Skipping issue #{issue.number} because it has a disabled page label.")
            return

        page_label = self.getSinglePageLabel(issue_labels)
        is_single_page = bool(page_label)
        if not is_single_page and ({"Draft", "草稿"}.intersection(issue_labels) or not self.getContentCategory(issue_labels)):
            print(f"Skipping issue #{issue.number} because it is an unpublished draft without a content category.")
            return
        listJsonName = 'singeListJson' if is_single_page else 'postListJson'

        fileName = self.createFileName(issue, postConfig, page_label=page_label)
        html_filename = f"{fileName}.html"

        if is_single_page:
            html_dir = self.root_dir + html_filename
            relative_url = html_filename
        else:
            html_dir = self.post_dir + html_filename
            relative_url = self.post_folder + html_filename

        post_data = {
            "htmlDir": html_dir,
            "labels": self.normalizeLabels(issue_labels),
            "contentCategory": self.getContentCategory(issue_labels),
            "postTitle": issue.title,
            "postUrl": f"{self.blogBase['homeUrl']}/{urllib.parse.quote(relative_url)}",
            "postSourceUrl": issue.html_url,
            "commentNum": issue.comments,
            "wordCount": len(body_content),
            "createdAt": int(postConfig.get("timestamp", time.mktime(issue.created_at.timetuple()))),
            "top": 0
        }

        for event in issue.get_events():
            if event.event == "pinned":
                post_data["top"] = 1
            elif event.event == "unpinned":
                post_data["top"] = 0

        if "description" in postConfig:
            post_data["description"] = postConfig["description"]
        else:
            period = "。" if self.blogBase["i18n"] == "CN" else "."
            first_sentence = body_content.split(period)[0]
            post_data["description"] = first_sentence.replace("\"", "\'") + period

        thisTime = datetime.datetime.fromtimestamp(post_data["createdAt"], tz=self.TZ)
        updatedTime = issue.updated_at.replace(tzinfo=datetime.timezone.utc).astimezone(self.TZ)
        post_data["createdDate"] = thisTime.strftime("%Y-%m-%d")
        post_data["isoDate"] = thisTime.isoformat()
        post_data["updatedDate"] = updatedTime.strftime("%Y-%m-%d")
        post_data["updatedIsoDate"] = updatedTime.isoformat()
        post_data["dateLabelColor"] = self.blogBase["yearColorList"][thisTime.year % len(self.blogBase["yearColorList"])]

        # [MODIFIED] Added "password" to allowed keys
        for key in ["style", "script", "head", "ogImage", "keywords", "quote", "daily_sentence", "password"]:
            post_data[key] = postConfig.get(key, self.blogBase.get(key, ""))

        self.blogBase[listJsonName][f"P{issue.number}"] = post_data

        mdFileName = re.sub(r'[<>:/\\|?*\"]|[\0-\31]', '-', issue.title)
        with open(os.path.join(self.backup_dir, f"{mdFileName}.md"), 'w', encoding='UTF-8') as f:
            f.write(body_content)

    def createFileName(self, issue, postConfig, page_label=""):
        if page_label:
            return page_label

        slug = postConfig.get("slug")
        if slug:
            return slug

        url_mode = self.blogBase.get("urlMode", "pinyin")
        if url_mode == "issue":
            return str(issue.number)
        elif url_mode == "ru_translit":
            return str(translit(issue.title, language_code='ru', reversed=True)).replace(' ', '-')
        else:
            return Pinyin().get_pinyin(issue.title)

    def createFeedXml(self):
        print("====== create rss xml ======")
        current_time = int(time.time())

        published_posts = {k: v for k, v in self.blogBase["postListJson"].items() if v["createdAt"] <= current_time}
        sorted_posts_for_feed = dict(sorted(published_posts.items(),key=lambda x:x[1]["createdAt"],reverse=True))

        feed = FeedGenerator()
        feed.title(self.blogBase["title"])
        feed.description(self.blogBase["subTitle"])
        feed.link(href=self.blogBase["homeUrl"])
        feed.image(url=f"{self.blogBase['homeUrl']}{self.blogBase['avatarUrl']}", title="avatar", link=self.blogBase["homeUrl"])
        feed.copyright(self.blogBase["title"])
        feed.managingEditor(self.blogBase["title"])
        feed.webMaster(self.blogBase["title"])
        feed.ttl("60")

        all_content_for_feed = list(self.blogBase["singeListJson"].values()) + list(sorted_posts_for_feed.values())
        all_content_for_feed.sort(key=lambda x: x["createdAt"], reverse=True)

        for item_data in all_content_for_feed:
            item = feed.add_item()
            item.guid(item_data["postUrl"], permalink=True)
            item.title(item_data["postTitle"])
            item.description(item_data["description"])
            item.link(href=item_data["postUrl"])
            item.pubDate(datetime.datetime.fromtimestamp(item_data["createdAt"], tz=datetime.timezone.utc))

            if item_data.get("ogImage"):
                image_url = item_data["ogImage"]
                mime_type = 'image/jpeg'
                if image_url.lower().endswith('.png'):
                    mime_type = 'image/png'
                elif image_url.lower().endswith('.gif'):
                    mime_type = 'image/gif'
                item.enclosure(url=image_url, length='0', type=mime_type)

        feed.rss_file(os.path.join(self.root_dir, 'rss.xml'), pretty=True)

    def createSitemapXml(self):
        print("====== create sitemap xml ======")
        current_time = int(time.time())
        urls = []

        def add_url(loc, lastmod=None, changefreq="weekly", priority="0.6"):
            urls.append({
                "loc": loc,
                "lastmod": lastmod or datetime.datetime.now(self.TZ).date().isoformat(),
                "changefreq": changefreq,
                "priority": priority
            })

        add_url(self.blogBase["homeUrl"], priority="1.0", changefreq="daily")
        add_url(f"{self.blogBase['homeUrl']}/tag.html", priority="0.7")
        add_url(f"{self.blogBase['homeUrl']}/subscribe.html", priority="0.7")
        add_url(f"{self.blogBase['homeUrl']}/about.html", priority="0.8")
        add_url(f"{self.blogBase['homeUrl']}/start.html", priority="0.8")
        for page in self.blogBase["singeListJson"].values():
            if page["createdAt"] <= current_time:
                add_url(page["postUrl"], page.get("updatedDate", page["createdDate"]), priority="0.8")

        for post in self.blogBase["postListJson"].values():
            if post["createdAt"] <= current_time:
                add_url(post["postUrl"], post.get("updatedDate", post["createdDate"]), priority="0.9")

        excluded_labels = set(self.blogBase["singlePage"]) | set(self.blogBase["hiddenPage"]) | set(self.blogBase.get("disabledPage", []))
        for label in self.blogBase.get("labelColorDict", {}).keys():
            if label not in excluded_labels:
                filename = f"{self.getLabelSlug(label)}.html"
                add_url(f"{self.blogBase['homeUrl']}/{filename}", priority="0.6")

        urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
        seen = set()
        for item in urls:
            if item["loc"] in seen:
                continue
            seen.add(item["loc"])
            url_el = ET.SubElement(urlset, "url")
            for key in ["loc", "lastmod", "changefreq", "priority"]:
                child = ET.SubElement(url_el, key)
                child.text = item[key]

        tree = ET.ElementTree(urlset)
        ET.indent(tree, space="  ", level=0)
        tree.write(os.path.join(self.root_dir, "sitemap.xml"), encoding="utf-8", xml_declaration=True)

    def createTagCloudPage(self):
        print("====== create tag cloud page ======")
        all_posts = list(self.blogBase["postListJson"].values())
        tag_info = {}
        max_count = 0
        excluded_labels = set(self.blogBase['singlePage']) | set(self.blogBase['hiddenPage']) | set(self.blogBase.get('disabledPage', []))

        for post in all_posts:
            for label in post['labels']:
                if label not in excluded_labels:
                    if label in tag_info:
                        tag_info[label]['count'] += 1
                    else:
                        filename = f"{self.getLabelSlug(label)}.html"
                        tag_info[label] = {
                            'count': 1,
                            'url': f"{self.blogBase['homeUrl']}/{filename}"
                        }

        if tag_info:
            max_count = max(info['count'] for info in tag_info.values())

        render_dict = self.blogBase.copy()
        render_dict["tag_info"] = OrderedDict(sorted(tag_info.items()))
        render_dict["maxTagsCount"] = max_count

        context = {
            'blogBase': render_dict,
            'i18n': self.i18n,
            'IconList': IconBase,
            'tag_info': render_dict['tag_info']
        }
        self.renderHtml('tag.html', context, f"{self.root_dir}tag.html")
        print("Created tag.html (Cloud Page)")

    def createTagPages(self):
        print("====== create single tag pages ======")
        all_posts = list(self.blogBase["postListJson"].values())
        all_tags = set()
        excluded_labels = set(self.blogBase['singlePage']) | set(self.blogBase['hiddenPage']) | set(self.blogBase.get('disabledPage', []))
        for post in all_posts:
            for label in post['labels']:
                if label not in excluded_labels:
                    all_tags.add(label)

        for tag in all_tags:
            posts_for_this_tag = sorted(
                [p for p in all_posts if tag in p['labels']],
                key=lambda x: x['createdAt'],
                reverse=True
            )

            post_count = len(posts_for_this_tag)
            page_size = self.blogBase["onePageListNum"]
            num_pages = (post_count + page_size - 1) // page_size or 1
            tag_pinyin = self.getLabelSlug(tag)

            for page_num in range(num_pages):
                start_index = page_num * page_size
                end_index = start_index + page_size
                paginated_posts = posts_for_this_tag[start_index:end_index]

                render_dict = self.blogBase.copy()
                render_dict["current_tag_name"] = tag

                if page_num == 0:
                    filename = f"{tag_pinyin}.html"
                    render_dict["canonicalUrl"] = f"{self.blogBase['homeUrl']}/{filename}"
                    render_dict["prevUrl"] = "disabled"
                else:
                    filename = f"{tag_pinyin}-page{page_num + 1}.html"
                    render_dict["canonicalUrl"] = f"{self.blogBase['homeUrl']}/{filename}"
                    render_dict["prevUrl"] = f"/{tag_pinyin}.html" if page_num == 1 else f"/{tag_pinyin}-page{page_num}.html"

                render_dict["nextUrl"] = f"/{tag_pinyin}-page{page_num + 2}.html" if end_index < post_count else "disabled"

                context = {
                    'blogBase': render_dict,
                    'i18n': self.i18n,
                    'IconList': IconBase,
                    'current_tag_name': tag,
                    'posts_for_tag': paginated_posts
                }

                html_path = os.path.join(self.root_dir, filename)
                self.renderHtml('tag_single.html', context, html_path)
                print(f"Created single tag page: {html_path}")

    def createSubscribePage(self):
        print("====== create subscribe page ======")
        render_dict = self.blogBase.copy()
        render_dict["canonicalUrl"] = f"{self.blogBase['homeUrl']}/subscribe.html"
        context = {
            'blogBase': render_dict,
            'i18n': self.i18n,
            'IconList': IconBase
        }
        self.renderHtml('subscribe.html', context, f"{self.root_dir}subscribe.html")

    def createLegacyCategoryRedirects(self):
        print("====== create legacy category redirects ======")
        for legacy_file, target_file in self.blogBase.get("legacyCategoryRedirects", {}).items():
            target_url = f"{self.blogBase['homeUrl']}/{target_file}"
            redirect_html = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="robots" content="noindex,follow">
<link rel="canonical" href="{target_url}">
<meta http-equiv="refresh" content="0;url={target_url}">
<title>页面已迁移</title></head>
<body><p>页面已迁移至 <a href="{target_url}">{target_url}</a>。</p></body></html>'''
            with open(os.path.join(self.root_dir, legacy_file), 'w', encoding='UTF-8') as f:
                f.write(redirect_html)

    def createStaticLandingPages(self):
        print("====== create static landing pages ======")
        pages = [
            ("about.html", "about.html"),
            ("start.html", "start.html"),
        ]
        for template_name, output_name in pages:
            render_dict = self.blogBase.copy()
            render_dict["canonicalUrl"] = f"{self.blogBase['homeUrl']}/{output_name}"
            context = {
                'blogBase': render_dict,
                'i18n': self.i18n,
                'IconList': IconBase
            }
            self.renderHtml(template_name, context, f"{self.root_dir}{output_name}")

    def createNotFoundPage(self):
        print("====== create 404 page ======")
        render_dict = self.blogBase.copy()
        render_dict["canonicalUrl"] = self.blogBase["homeUrl"]
        context = {
            'blogBase': render_dict,
            'i18n': self.i18n,
            'IconList': IconBase
        }
        self.renderHtml('404.html', context, f"{self.root_dir}404.html")

    def runAll(self):
        print("====== start create static html ======")
        # [关键修正] 运行前清空旧的文章列表数据
        self.blogBase["postListJson"] = {}
        self.blogBase["singeListJson"] = {}
        self.cleanFile()
        self.syncStaticAssets()

        issues = self.repo.get_issues(state='open')
        for issue in issues:
            self.addOnePostJson(issue)

        self.validateContentCategories()
        self.enrichPostNavigation()
        all_pages = list(self.blogBase["postListJson"].values()) + list(self.blogBase["singeListJson"].values())
        for page_data in all_pages:
            self.createPostHtml(page_data)

        self.createPlistHtml()
        self.createTagCloudPage()
        self.createTagPages()
        self.createLegacyCategoryRedirects()
        self.createSubscribePage()
        self.createStaticLandingPages()
        self.createNotFoundPage()
        self.createFeedXml()
        self.createSitemapXml()

        print("====== create static html end ======")

    def runOne(self, number_str):
        print(f"====== start create static html for issue {number_str} ======")
        # [关键修正] 运行前清空旧的文章列表数据
        self.blogBase["postListJson"] = {}
        self.blogBase["singeListJson"] = {}
        # [关键修改] runOne 也需要同步静态文件，以发布新图片
        self.syncStaticAssets()

        issue = self.repo.get_issue(int(number_str))
        if issue.state == "open":
            issues = self.repo.get_issues(state='open')
            for i in issues:
                self.addOnePostJson(i)
            self.validateContentCategories()
            self.enrichPostNavigation()

            is_single_page = bool(self.getSinglePageLabel(issue.labels))
            listJsonName = 'singeListJson' if is_single_page else 'postListJson'

            if f"P{number_str}" in self.blogBase[listJsonName]:
                 self.createPostHtml(self.blogBase[listJsonName][f"P{number_str}"])

            self.createPlistHtml()
            self.createTagCloudPage()
            self.createTagPages()
            self.createLegacyCategoryRedirects()
            self.createSubscribePage()
            self.createStaticLandingPages()
            self.createNotFoundPage()
            self.createFeedXml()
            self.createSitemapXml()
            print("====== create static html end ======")
        else:
            print("====== issue is closed ======")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("github_token", help="github_token")
    parser.add_argument("repo_name", help="repo_name")
    parser.add_argument("--issue_number", help="issue_number", default="0", required=False)
    options = parser.parse_args()

    blog = GMEEK(options)

    if os.path.exists("blogBase.json"):
        with open("blogBase.json", "r", encoding='utf-8') as f:
            try:
                oldBlogBase = json.load(f)
                blog.blogBase["postListJson"] = oldBlogBase.get("postListJson", {})
                blog.blogBase["singeListJson"] = oldBlogBase.get("singeListJson", {})
            except json.JSONDecodeError:
                print("Warning: blogBase.json is corrupted. Starting fresh.")

    if options.issue_number == "0" or not options.issue_number:
        blog.runAll()
    else:
        blog.runOne(options.issue_number)

    with open("blogBase.json", "w", encoding='utf-8') as f:
        json.dump(blog.blogBase, f, ensure_ascii=False, indent=2)

    print("====== create postList.json file ======")
    current_time = int(time.time())
    published_posts = {k: v for k, v in blog.blogBase["postListJson"].items() if v["createdAt"] <= current_time}
    blog.blogBase["postListJson"] = dict(sorted(published_posts.items(), key=lambda x:x[1]["createdAt"], reverse=True))

    commentNumSum=0
    wordCount=0
    for i in list(blog.blogBase["postListJson"].keys()):
        del blog.blogBase["postListJson"][i]["description"]
        del blog.blogBase["postListJson"][i]["postSourceUrl"]
        del blog.blogBase["postListJson"][i]["htmlDir"]
        del blog.blogBase["postListJson"][i]["createdAt"]
        del blog.blogBase["postListJson"][i]["script"]
        del blog.blogBase["postListJson"][i]["style"]
        del blog.blogBase["postListJson"][i]["top"]
        del blog.blogBase["postListJson"][i]["ogImage"]
        if 'head' in blog.blogBase["postListJson"][i]: del blog.blogBase["postListJson"][i]["head"]
        if 'keywords' in blog.blogBase["postListJson"][i]: del blog.blogBase["postListJson"][i]["keywords"]
        if 'isoDate' in blog.blogBase["postListJson"][i]: del blog.blogBase["postListJson"][i]["isoDate"]
        if 'quote' in blog.blogBase["postListJson"][i]: del blog.blogBase["postListJson"][i]["quote"]
        if 'daily_sentence' in blog.blogBase["postListJson"][i]: del blog.blogBase["postListJson"][i]["daily_sentence"]
        if 'commentNum' in blog.blogBase["postListJson"][i]:
            commentNumSum += blog.blogBase["postListJson"][i]["commentNum"]
            del blog.blogBase["postListJson"][i]["commentNum"]
        if 'wordCount' in blog.blogBase["postListJson"][i]:
            wordCount += blog.blogBase["postListJson"][i]["wordCount"]
            del blog.blogBase["postListJson"][i]["wordCount"]

    blog.blogBase["postListJson"]["labelColorDict"]=blog.labelColorDict
    with open(os.path.join(blog.root_dir, "postList.json"), "w") as f:
        json.dump(blog.blogBase["postListJson"], f, ensure_ascii=False)

    if os.environ.get('GITHUB_EVENT_NAME') != 'schedule':
        print("====== update readme file ======")
        workspace_path = os.environ.get('GITHUB_WORKSPACE', '.')
        post_count = len(published_posts)
        readme = (
            f"# {blog.blogBase['title']} :link: {blog.blogBase['homeUrl']} \r\n"
            f"## [网站调试日志]({blog.blogBase['homeUrl']}/post/debugging-log.html)\r\n"
            f"### :page_facing_up: [{post_count}]({blog.blogBase['homeUrl']}/tag.html) \r\n"
            f"### :speech_balloon: {commentNumSum} \r\n"
            f"### :hibiscus: {wordCount} \r\n"
            f"### :alarm_clock: {datetime.datetime.now(blog.TZ).strftime('%Y-%m-%d %H:%M:%S')} \r\n"
            f"### Powered by :heart: [莫白来]({blog.blogBase['homeUrl']})\r\n"
        )
        with open(os.path.join(workspace_path, "README.md"), "w", encoding='utf-8') as f:
            f.write(readme)
