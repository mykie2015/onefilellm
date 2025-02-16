import requests
from bs4 import BeautifulSoup, Comment
from urllib.parse import urljoin, urlparse
from PyPDF2 import PdfReader
import os
import sys
import tiktoken
import nltk
from nltk.corpus import stopwords
import re
import nbformat
from nbconvert import PythonExporter
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import pyperclip
import wget
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich.progress import Progress, TextColumn, BarColumn, TimeRemainingColumn
import xml.etree.ElementTree as ET
import logging
from datetime import datetime
import hashlib
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug.log'),
        logging.StreamHandler()
    ]
)

EXCLUDED_DIRS = ["dist", "node_modules", ".git", "__pycache__"]  # Add any other directories to exclude here

def safe_file_read(filepath, fallback_encoding='latin1'):
    try:
        with open(filepath, "r", encoding='utf-8') as file:
            return file.read()
    except UnicodeDecodeError:
        with open(filepath, "r", encoding=fallback_encoding) as file:
            return file.read()

nltk.download("stopwords", quiet=True)
stop_words = set(stopwords.words("english"))

load_dotenv()  # Load environment variables from .env file
TOKEN = os.getenv('GITHUB_TOKEN')
if not TOKEN:
    raise EnvironmentError("GITHUB_TOKEN not found in .env file. Please add it as: GITHUB_TOKEN=your_token_here")

headers = {"Authorization": f"token {TOKEN}"}

def download_file(url, target_path):
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    with open(target_path, "wb") as f:
        f.write(response.content)

def process_ipynb_file(temp_file):
    with open(temp_file, "r", encoding='utf-8', errors='ignore') as f:
        notebook_content = f.read()

    exporter = PythonExporter()
    python_code, _ = exporter.from_notebook_node(nbformat.reads(notebook_content, as_version=4))
    return python_code

def process_directory(url, output):
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    files = response.json()

    for file in files:
        if file["type"] == "dir" and file["name"] in EXCLUDED_DIRS:
            continue  # Skip excluded directories

        if file["type"] == "file" and is_allowed_filetype(file["name"]):
            print(f"Processing {file['path']}...")

            temp_file = f"temp_{file['name']}"
            download_file(file["download_url"], temp_file)

            output.write(f"# {'-' * 3}\n")
            output.write(f"# Filename: {file['path']}\n")
            output.write(f"# {'-' * 3}\n\n")

            if file["name"].endswith(".ipynb"):
                output.write(process_ipynb_file(temp_file))
            else:
                with open(temp_file, "r", encoding='utf-8', errors='ignore') as f:
                    output.write(f.read())

            output.write("\n\n")
            os.remove(temp_file)
        elif file["type"] == "dir":
            process_directory(file["url"], output)

def process_local_directory(local_path, output):
    for root, dirs, files in os.walk(local_path):
        # Modify dirs in-place to exclude specified directories
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for file in files:
            if is_allowed_filetype(file):
                print(f"Processing {os.path.join(root, file)}...")

                output.write(f"# {'-' * 3}\n")
                output.write(f"# Filename: {os.path.join(root, file)}\n")
                output.write(f"# {'-' * 3}\n\n")

                file_path = os.path.join(root, file)

                if file.endswith(".ipynb"):
                    output.write(process_ipynb_file(file_path))
                else:
                    with open(file_path, "r", encoding='utf-8', errors='ignore') as f:
                        output.write(f.read())

                output.write("\n\n")

def process_github_repo(repo_url):
    api_base_url = "https://api.github.com/repos/"
    repo_url_parts = repo_url.split("https://github.com/")[-1].split("/")
    repo_name = "/".join(repo_url_parts[:2])

    # Detect if we have a branch or tag reference
    branch_or_tag = ""
    subdirectory = ""
    if len(repo_url_parts) > 2 and repo_url_parts[2] == "tree":
        # The branch or tag name should be at index 3
        if len(repo_url_parts) > 3:
            branch_or_tag = repo_url_parts[3]
        # Any remaining parts after the branch/tag name form the subdirectory
        if len(repo_url_parts) > 4:
            subdirectory = "/".join(repo_url_parts[4:])
    
    contents_url = f"{api_base_url}{repo_name}/contents"
    if subdirectory:
        contents_url = f"{contents_url}/{subdirectory}"
    if branch_or_tag:
        contents_url = f"{contents_url}?ref={branch_or_tag}"

    repo_content = [f'<source type="github_repository" url="{repo_url}">']

    def process_directory(url, repo_content):
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        files = response.json()

        for file in files:
            if file["type"] == "dir" and file["name"] in EXCLUDED_DIRS:
                continue

            if file["type"] == "file" and is_allowed_filetype(file["name"]):

                print(f"Processing {file['path']}...")

                temp_file = f"temp_{file['name']}"
                download_file(file["download_url"], temp_file)

                repo_content.append(f'<file name="{escape_xml(file["path"])}">') 
                if file["name"].endswith(".ipynb"):
                    repo_content.append(escape_xml(process_ipynb_file(temp_file)))
                else:
                    with open(temp_file, "r", encoding='utf-8', errors='ignore') as f:
                        repo_content.append(escape_xml(f.read()))
                repo_content.append('</file>')
                os.remove(temp_file)

            elif file["type"] == "dir":
                process_directory(file["url"], repo_content)

    process_directory(contents_url, repo_content)
    repo_content.append('</source>')
    print("All files processed.")

    return "\n".join(repo_content)

def process_local_folder(local_path):
    logging.info(f"Starting process_local_folder with path: {local_path}")
    
    def process_local_directory(local_path):
        logging.info(f"Processing directory: {local_path}")
        content = [f'<source type="local_directory" path="{escape_xml(local_path)}">']
        
        try:
            for root, dirs, files in os.walk(local_path):
                logging.debug(f"Walking directory: {root}")
                logging.debug(f"Found directories: {dirs}")
                logging.debug(f"Found files: {files}")
                
                # Exclude directories
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                logging.debug(f"After exclusion, processing directories: {dirs}")

                for file in files:
                    if is_allowed_filetype(file):
                        logging.info(f"Processing file: {os.path.join(root, file)}")

                        try:
                            file_path = os.path.join(root, file)
                            relative_path = os.path.relpath(file_path, local_path)
                            content.append(f'<file name="{escape_xml(relative_path)}">')

                            if file.endswith(".ipynb"):
                                content.append(escape_xml(process_ipynb_file(file_path)))
                            else:
                                with open(file_path, "r", encoding='utf-8', errors='ignore') as f:
                                    content.append(escape_xml(f.read()))

                            content.append('</file>')
                        except Exception as e:
                            logging.error(f"Error processing file {file}: {str(e)}")

        except Exception as e:
            logging.error(f"Error walking directory {local_path}: {str(e)}")
            raise

        content.append('</source>')
        return '\n'.join(content)

    try:
        formatted_content = process_local_directory(local_path)
        logging.info("All files processed successfully")
        return formatted_content
    except Exception as e:
        logging.error(f"Fatal error in process_local_folder: {str(e)}")
        raise

def process_arxiv_pdf(arxiv_abs_url):
    pdf_url = arxiv_abs_url.replace("/abs/", "/pdf/") + ".pdf"
    response = requests.get(pdf_url)
    pdf_content = response.content

    with open('temp.pdf', 'wb') as pdf_file:
        pdf_file.write(pdf_content)

    text = []
    with open('temp.pdf', 'rb') as pdf_file:
        pdf_reader = PdfReader(pdf_file)
        for page in range(len(pdf_reader.pages)):
            text.append(pdf_reader.pages[page].extract_text())

    formatted_text = f'<source type="arxiv_paper" url="{arxiv_abs_url}">\n'
    formatted_text += '<paper>\n'
    formatted_text += escape_xml(' '.join(text))
    formatted_text += '\n</paper>\n'
    formatted_text += '</source>'

    os.remove('temp.pdf')
    print("ArXiv paper processed successfully.")

    return formatted_text

def extract_links(input_file, output_file):
    url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    
    with open(input_file, 'r', encoding='utf-8') as file:
        content = file.read()
        urls = re.findall(url_pattern, content)
    
    with open(output_file, 'w', encoding='utf-8') as output:
        for url in urls:
            output.write(url + '\n')

def fetch_youtube_transcript(url):
    logging.info(f"Fetching transcript for: {url}")
    
    def extract_video_id(url):
        pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        return None

    video_id = extract_video_id(url)
    logging.debug(f"Extracted video ID: {video_id}")

    if not video_id:
        return f'<source type="youtube_transcript" url="{escape_xml(url)}">\n<error>Invalid YouTube URL format</error>\n</source>'

    try:
        # Try to get all available transcripts first
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        logging.debug(f"Available transcripts: {transcript_list}")

        # Try English first, fall back to auto-generated
        try:
            transcript = transcript_list.find_transcript(['en'])
        except:
            try:
                transcript = transcript_list.find_generated_transcript(['en'])
            except:
                # Last resort: get the first available transcript
                transcript = transcript_list.find_manually_created_transcript()

        # Get the actual transcript data
        transcript_data = transcript.fetch()
        
        # Format transcript text
        formatted_text = []
        for entry in transcript_data:
            formatted_text.append(f"{entry['text']}")
        
        transcript_content = ' '.join(formatted_text)
        
        return f'''<source type="youtube_transcript" url="{escape_xml(url)}">
<transcript>
{escape_xml(transcript_content)}
</transcript>
</source>'''

    except Exception as e:
        error_message = f"Failed to fetch transcript: {str(e)}"
        logging.error(error_message)
        return f'<source type="youtube_transcript" url="{escape_xml(url)}">\n<error>{escape_xml(error_message)}</error>\n</source>'

def preprocess_text(input_file, output_file):
    with open(input_file, "r", encoding="utf-8") as input_file:
        input_text = input_file.read()

    def process_text(text):
        text = re.sub(r"[\n\r]+", "\n", text)
        # Update the following line to include apostrophes and quotation marks
        text = re.sub(r"[^a-zA-Z0-9\s_.,!?:;@#$%^&*()+\-=[\]{}|\\<>`~'\"/]+", "", text)
        text = re.sub(r"\s+", " ", text)
        text = text.lower()
        words = text.split()
        words = [word for word in words if word not in stop_words]
        return " ".join(words)

    try:
        # Try to parse the input as XML
        root = ET.fromstring(input_text)

        # Process text content while preserving XML structure
        for elem in root.iter():
            if elem.text:
                elem.text = process_text(elem.text)
            if elem.tail:
                elem.tail = process_text(elem.tail)

        # Write the processed XML to the output file
        tree = ET.ElementTree(root)
        tree.write(output_file, encoding="utf-8", xml_declaration=True)
        print("Text preprocessing completed with XML structure preserved.")
    except ET.ParseError:
        # If XML parsing fails, process the text without preserving XML structure
        processed_text = process_text(input_text)
        with open(output_file, "w", encoding="utf-8") as out_file:
            out_file.write(processed_text)
        print("XML parsing failed. Text preprocessing completed without XML structure.")

def get_token_count(text, disallowed_special=[], chunk_size=1000):
    enc = tiktoken.get_encoding("cl100k_base")

    # Remove XML tags
    text_without_tags = re.sub(r'<[^>]+>', '', text)

    # Split the text into smaller chunks
    chunks = [text_without_tags[i:i+chunk_size] for i in range(0, len(text_without_tags), chunk_size)]
    total_tokens = 0

    for chunk in chunks:
        tokens = enc.encode(chunk, disallowed_special=disallowed_special)
        total_tokens += len(tokens)
    
    return total_tokens

def is_same_domain(base_url, new_url):
    return urlparse(base_url).netloc == urlparse(new_url).netloc

def is_within_depth(base_url, current_url, max_depth):
    base_parts = urlparse(base_url).path.rstrip('/').split('/')
    current_parts = urlparse(current_url).path.rstrip('/').split('/')

    if current_parts[:len(base_parts)] != base_parts:
        return False

    return len(current_parts) - len(base_parts) <= max_depth

def process_pdf(url):
    response = requests.get(url)
    response.raise_for_status()

    with open('temp.pdf', 'wb') as pdf_file:
        pdf_file.write(response.content)

    text = []
    with open('temp.pdf', 'rb') as pdf_file:
        pdf_reader = PdfReader(pdf_file)
        for page in range(len(pdf_reader.pages)):
            text.append(pdf_reader.pages[page].extract_text())

    os.remove('temp.pdf')
    return ' '.join(text)

def crawl_and_extract_text(base_url, max_depth, include_pdfs, ignore_epubs):
    visited_urls = set()
    urls_to_visit = [(base_url, 0)]
    processed_urls = []
    all_text = [f'<source type="web_documentation" url="{escape_xml(base_url)}">']

    while urls_to_visit:
        current_url, current_depth = urls_to_visit.pop(0)
        clean_url = current_url.split('#')[0]

        if clean_url not in visited_urls and is_same_domain(base_url, clean_url) and is_within_depth(base_url, clean_url, max_depth):
            if ignore_epubs and clean_url.endswith('.epub'):
                continue

            try:
                response = requests.get(current_url)
                soup = BeautifulSoup(response.content, 'html.parser')
                visited_urls.add(clean_url)

                if clean_url.endswith('.pdf') and include_pdfs:
                    text = process_pdf(clean_url)
                else:
                    for element in soup(['script', 'style', 'head', 'title', 'meta', '[document]']):
                        element.decompose()
                    comments = soup.find_all(string=lambda text: isinstance(text, Comment))
                    for comment in comments:
                        comment.extract()
                    text = soup.get_text(separator='\n', strip=True)

                all_text.append(f'<page url="{escape_xml(clean_url)}">')
                all_text.append(escape_xml(text))
                all_text.append('</page>')
                processed_urls.append(clean_url)
                print(f"Processed: {clean_url}")

                if current_depth < max_depth:
                    for link in soup.find_all('a', href=True):
                        new_url = urljoin(current_url, link['href']).split('#')[0]
                        if new_url not in visited_urls and is_within_depth(base_url, new_url, max_depth) and (include_pdfs or not new_url.endswith('.pdf')) and not (ignore_epubs and new_url.endswith('.epub')):
                            urls_to_visit.append((new_url, current_depth + 1))

            except requests.RequestException as e:
                print(f"Failed to retrieve {clean_url}: {e}")

    all_text.append('</source>')
    formatted_content = '\n'.join(all_text)

    return {
        'content': formatted_content,
        'processed_urls': processed_urls
    }

def process_doi_or_pmid(identifier):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
        'Connection': 'keep-alive'
    }

    try:
        payload = {
            'sci-hub-plugin-check': '',
            'request': identifier
        }

        base_url = 'https://sci-hub.se/'
        response = requests.post(base_url, headers=headers, data=payload, timeout=60)
        soup = BeautifulSoup(response.content, 'html.parser')
        pdf_element = soup.find(id='pdf')

        if pdf_element is None:
            raise ValueError(f"No PDF found for identifier {identifier}. Sci-hub might be inaccessible or the document is not available.")

        content = pdf_element.get('src').replace('#navpanes=0&view=FitH', '').replace('//', '/')

        if content.startswith('/downloads'):
            pdf_url = 'https://sci-hub.se' + content
        elif content.startswith('/tree'):
            pdf_url = 'https://sci-hub.se' + content
        elif content.startswith('/uptodate'):
            pdf_url = 'https://sci-hub.se' + content
        else:
            pdf_url = 'https:/' + content

        pdf_filename = f"{identifier.replace('/', '-')}.pdf"
        wget.download(pdf_url, pdf_filename)

        with open(pdf_filename, 'rb') as pdf_file:
            pdf_reader = PdfReader(pdf_file)
            text = ""
            for page in range(len(pdf_reader.pages)):
                text += pdf_reader.pages[page].extract_text()

        formatted_text = f'<source type="sci_hub_paper" identifier="{escape_xml(identifier)}">\n'
        formatted_text += '<paper>\n'
        formatted_text += escape_xml(text)
        formatted_text += '\n</paper>\n'
        formatted_text += '</source>'

        os.remove(pdf_filename)
        print(f"Identifier {identifier} processed successfully.")
        return formatted_text
    except (requests.RequestException, ValueError) as e:
        error_text = f'<source type="sci_hub_paper" identifier="{escape_xml(identifier)}">\n'
        error_text += f'<error>{escape_xml(str(e))}</error>\n'
        error_text += '</source>'
        print(f"Error processing identifier {identifier}: {str(e)}")
        print("Sci-hub appears to be inaccessible or the document was not found. Please try again later.")
        return error_text
        
def process_github_pull_request(pull_request_url):
    url_parts = pull_request_url.split("/")
    repo_owner = url_parts[3]
    repo_name = url_parts[4]
    pull_request_number = url_parts[-1]

    api_base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/pulls/{pull_request_number}"
    headers = {"Authorization": f"token {TOKEN}"}

    response = requests.get(api_base_url, headers=headers)
    pull_request_data = response.json()

    diff_url = pull_request_data["diff_url"]
    diff_response = requests.get(diff_url, headers=headers)
    pull_request_diff = diff_response.text

    comments_url = pull_request_data["comments_url"]
    review_comments_url = pull_request_data["review_comments_url"]
    comments_response = requests.get(comments_url, headers=headers)
    review_comments_response = requests.get(review_comments_url, headers=headers)
    comments_data = comments_response.json()
    review_comments_data = review_comments_response.json()

    all_comments = comments_data + review_comments_data
    all_comments.sort(key=lambda comment: comment.get("position") or float("inf"))

    formatted_text = f'<source type="github_pull_request" url="{pull_request_url}">\n'
    formatted_text += '<pull_request_info>\n'
    formatted_text += f'<title>{escape_xml(pull_request_data["title"])}</title>\n'
    formatted_text += f'<description>{escape_xml(pull_request_data["body"])}</description>\n'
    formatted_text += '<merge_details>\n'
    formatted_text += f'{escape_xml(pull_request_data["user"]["login"])} wants to merge {pull_request_data["commits"]} commit into {repo_owner}:{pull_request_data["base"]["ref"]} from {pull_request_data["head"]["label"]}\n'
    formatted_text += '</merge_details>\n'
    formatted_text += '<diff_and_comments>\n'

    diff_lines = pull_request_diff.split("\n")
    comment_index = 0
    for line in diff_lines:
        formatted_text += f'{escape_xml(line)}\n'
        while comment_index < len(all_comments) and all_comments[comment_index].get("position") == diff_lines.index(line):
            comment = all_comments[comment_index]
            formatted_text += f'<review_comment>\n'
            formatted_text += f'<author>{escape_xml(comment["user"]["login"])}</author>\n'
            formatted_text += f'<content>{escape_xml(comment["body"])}</content>\n'
            formatted_text += f'<path>{escape_xml(comment["path"])}\n'
            formatted_text += f'<line>{comment["original_line"]}</line>\n'
            formatted_text += '</review_comment>\n'
            comment_index += 1

    formatted_text += '</diff_and_comments>\n'
    formatted_text += '</pull_request_info>\n'

    repo_url = f"https://github.com/{repo_owner}/{repo_name}"
    repo_content = process_github_repo(repo_url)
    
    formatted_text += '<repository>\n'
    formatted_text += repo_content
    formatted_text += '</repository>\n'
    formatted_text += '</source>'

    print(f"Pull request {pull_request_number} and repository content processed successfully.")

    return formatted_text
    
def escape_xml(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        # Remove the following lines to stop converting apostrophes and quotes
        # .replace("\"", "&quot;")
        # .replace("'", "&apos;")
    )

def process_github_issue(issue_url):
    url_parts = issue_url.split("/")
    repo_owner = url_parts[3]
    repo_name = url_parts[4]
    issue_number = url_parts[-1]

    api_base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{issue_number}"
    headers = {"Authorization": f"token {TOKEN}"}

    response = requests.get(api_base_url, headers=headers)
    issue_data = response.json()

    comments_url = issue_data["comments_url"]
    comments_response = requests.get(comments_url, headers=headers)
    comments_data = comments_response.json()

    formatted_text = f'<source type="github_issue" url="{issue_url}">\n'
    formatted_text += '<issue_info>\n'
    formatted_text += f'<title>{escape_xml(issue_data["title"])}</title>\n'
    formatted_text += f'<description>{escape_xml(issue_data["body"])}</description>\n'
    formatted_text += '<comments>\n'

    for comment in comments_data:
        formatted_text += '<comment>\n'
        formatted_text += f'<author>{escape_xml(comment["user"]["login"])}\n'
        formatted_text += f'<content>{escape_xml(comment["body"])}\n'

        code_snippets = re.findall(r'https://github.com/.*#L\d+-L\d+', comment['body'])
        for snippet_url in code_snippets:
            url_parts = snippet_url.split("#")
            file_url = url_parts[0].replace("/blob/", "/raw/")
            line_range = url_parts[1]
            start_line, end_line = map(int, line_range.split("-")[0][1:]), map(int, line_range.split("-")[1][1:])

            file_response = requests.get(file_url, headers=headers)
            file_content = file_response.text

            code_lines = file_content.split("\n")[start_line-1:end_line]
            code_snippet = "\n".join(code_lines)

            formatted_text += '<code_snippet>\n'
            formatted_text += f'<![CDATA[{code_snippet}]]>\n'
            formatted_text += '</code_snippet>\n'

        formatted_text += '</comment>\n'

    formatted_text += '</comments>\n'
    formatted_text += '</issue_info>\n'

    repo_url = f"https://github.com/{repo_owner}/{repo_name}"
    repo_content = process_github_repo(repo_url)
    
    formatted_text += '<repository>\n'
    formatted_text += repo_content
    formatted_text += '</repository>\n'
    formatted_text += '</source>'

    print(f"Issue {issue_number} and repository content processed successfully.")

    return formatted_text


def is_excluded_file(filename):
    """
    Check if a file should be excluded based on patterns.

    Args:
        filename (str): The file path to check

    Returns:
        bool: True if the file should be excluded, False otherwise
    """
    excluded_patterns = [
        '.pb.go',  # Proto generated Go files
        '_grpc.pb.go',  # gRPC generated Go files
        'mock_',  # Mock files
        '/generated/',  # Generated files in a generated directory
        '/mocks/',  # Mock files in a mocks directory
        '.gen.',  # Generated files with .gen. in name
        '_generated.',  # Generated files with _generated in name
        '.venv/',  # Virtual environment directory
        '.outputs/',  # Outputs directory
        '__pycache__',  # Python cache directory
    ]

    return any(pattern in filename for pattern in excluded_patterns)


def is_allowed_filetype(filename):
    """
    Check if a file should be processed based on its extension and exclusion patterns.

    Args:
        filename (str): The file path to check

    Returns:
        bool: True if the file should be processed, False otherwise
    """
    # First check if file matches any exclusion patterns
    if is_excluded_file(filename):
        return False

    # Then check if it has an allowed extension
    allowed_extensions = [
        '.go',
        '.proto',
        '.py',
        '.txt',
        '.md',
        '.cjs',
        '.html',
        '.json',
        '.ipynb',
        '.h',
        '.localhost',
        '.yaml',
        '.example'
    ]

    return any(filename.endswith(ext) for ext in allowed_extensions)

def create_output_folder(input_path):
    """
    Create a meaningful output folder name based on input path.
    For GitHub URLs, use 'github_<owner>_<repo>' when possible.
    """
    outputs_dir = "outputs"
    if not os.path.exists(outputs_dir):
        os.makedirs(outputs_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if os.path.isdir(input_path):
        folder_name = os.path.basename(os.path.abspath(input_path))
    else:
        parsed_url = urlparse(input_path)
        # Use a meaningful name for GitHub retrieval
        if parsed_url.scheme in ["http", "https"] and "github.com" in parsed_url.netloc:
            path_parts = parsed_url.path.strip("/").split("/")
            if len(path_parts) >= 2:
                folder_name = f"github_{path_parts[0]}_{path_parts[1]}"
            else:
                folder_name = "github_unknown"
        elif parsed_url.scheme in ["http", "https"]:
            domain = parsed_url.netloc.replace(".", "_")
            path_hash = hashlib.md5(parsed_url.path.encode()).hexdigest()[:8]
            folder_name = f"{domain}_{path_hash}"
        else:
            # Fallback for non-URL inputs
            folder_name = input_path.replace(" ", "_")

    output_folder = os.path.join(outputs_dir, f"{folder_name}_{timestamp}")
    os.makedirs(output_folder)
    return output_folder

def main():
    logging.info("Starting main function")
    console = Console()

    intro_text = Text("\nInput Paths or URLs Processed:\n", style="dodger_blue1")
    input_types = [
        ("• Local folder path (flattens all files into text)", "bright_white"),
        ("• GitHub repository URL (flattens all files into text)", "bright_white"),
        ("• GitHub pull request URL (PR + Repo)", "bright_white"),
        ("• GitHub issue URL (Issue + Repo)", "bright_white"),
        ("• Documentation URL (base URL)", "bright_white"),
        ("• YouTube video URL (to fetch transcript)", "bright_white"),
        ("• ArXiv Paper URL", "bright_white"),
        ("• DOI or PMID to search on Sci-Hub", "bright_white"),
    ]

    for input_type, color in input_types:
        intro_text.append(f"\n{input_type}", style=color)

    intro_panel = Panel(
        intro_text,
        expand=False,
        border_style="bold",
        title="[bright_white]Copy to File and Clipboard[/bright_white]",
        title_align="center",
        padding=(1, 1),
    )
    console.print(intro_panel)

    logging.debug(f"System arguments: {sys.argv}")
    
    if len(sys.argv) > 1:
        input_path = sys.argv[2] if sys.argv[1] == "--source" else sys.argv[1]
        logging.info(f"Using command line argument path: {input_path}")
    else:
        input_path = Prompt.ask("\n[bold dodger_blue1]Enter the path or URL[/bold dodger_blue1]", console=console)
        logging.info(f"Using prompted path: {input_path}")
    
    console.print(f"\n[bold bright_green]You entered:[/bold bright_green] [bold bright_yellow]{input_path}[/bold bright_yellow]\n")

    output_folder = create_output_folder(input_path)
    output_file = os.path.join(output_folder, "uncompressed_output.txt")
    processed_file = os.path.join(output_folder, "compressed_output.txt")
    urls_list_file = os.path.join(output_folder, "processed_urls.txt")

    with Progress(
        TextColumn("[bold bright_blue]{task.description}"),
        BarColumn(bar_width=None),
        TimeRemainingColumn(),
        console=console,
    ) as progress:

        task = progress.add_task("[bright_blue]Processing...", total=100)

        try:
            logging.info(f"Processing input path: {input_path}")
            
            if "github.com" in input_path:
                logging.debug("Detected GitHub URL")
                if "/pull/" in input_path:
                    final_output = process_github_pull_request(input_path)
                elif "/issues/" in input_path:
                    final_output = process_github_issue(input_path)
                else:
                    final_output = process_github_repo(input_path)
            elif urlparse(input_path).scheme in ["http", "https"]:
                if "youtube.com" in input_path or "youtu.be" in input_path:
                    final_output = fetch_youtube_transcript(input_path)
                elif "arxiv.org" in input_path:
                    final_output = process_arxiv_pdf(input_path)
                else:
                    crawl_result = crawl_and_extract_text(input_path, max_depth=2, include_pdfs=True, ignore_epubs=True)
                    final_output = crawl_result['content']
                    with open(urls_list_file, 'w', encoding='utf-8') as urls_file:
                        urls_file.write('\n'.join(crawl_result['processed_urls']))
            elif input_path.startswith("10.") and "/" in input_path or input_path.isdigit():
                final_output = process_doi_or_pmid(input_path)
            else:
                logging.debug("Processing as local folder")
                final_output = process_local_folder(input_path)

            progress.update(task, advance=50)

            # Write the uncompressed output
            with open(output_file, "w", encoding="utf-8") as file:
                file.write(final_output)
                logging.info(f"Wrote uncompressed output to {output_file}")


            # Process the compressed output
            preprocess_text(output_file, processed_file)

            progress.update(task, advance=50)

            compressed_text = safe_file_read(processed_file)
            compressed_token_count = get_token_count(compressed_text)
            console.print(f"\n[bright_green]Compressed Token Count:[/bright_green] [bold bright_cyan]{compressed_token_count}[/bold bright_cyan]")

            uncompressed_text = safe_file_read(output_file)
            uncompressed_token_count = get_token_count(uncompressed_text)
            console.print(f"[bright_green]Uncompressed Token Count:[/bright_green] [bold bright_cyan]{uncompressed_token_count}[/bold bright_cyan]")

            console.print(f"\n[bold bright_yellow]{processed_file}[/bold bright_yellow] and [bold bright_blue]{output_file}[/bold bright_blue] have been created in the working directory.")

            pyperclip.copy(uncompressed_text)
            console.print(f"\n[bright_white]The contents of [bold bright_blue]{output_file}[/bold bright_blue] have been copied to the clipboard.[/bright_white]")

        except Exception as e:
            logging.error(f"Error in main function: {str(e)}")
            console.print(f"\n[bold red]An error occurred:[/bold red] {str(e)}")
            console.print("\nPlease check your input and try again.")
            raise  # Re-raise the exception for debugging purposes
        
if __name__ == "__main__":
    main()
