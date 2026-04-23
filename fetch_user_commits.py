import os
import sys
import json
import urllib.request
import urllib.error
import datetime
import time
import csv

def make_request(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8')), response.getcode()
    except urllib.error.HTTPError as e:
        # Search API rate limit usually returns 403
        if e.code == 403:
            return None, e.code
        try:
            return json.loads(e.read().decode('utf-8')), e.code
        except json.JSONDecodeError:
            return None, e.code
    except Exception as e:
        print(f"Request failed: {e}")
        return None, 500

def get_user_commits(username, headers, since_date):
    commits_data = []
    page = 1
    while True:
        # The search API is used to find commits across all repositories.
        # It requires the cloak-preview accept header in some GitHub Enterprise Server versions,
        # but on public GitHub it works well and is highly rate-limited.
        url = f"https://api.github.com/search/commits?q=author:{username}+committer-date:>{since_date}&page={page}&per_page=100"
        data, status = make_request(url, headers)
        
        if status == 403:
            print(f"Rate limit hit or forbidden fetching commits for {username}. Waiting 60 seconds...")
            time.sleep(60)
            continue # Retry the same page
        elif status != 200:
            print(f"Error fetching commits for {username}. Status code: {status}")
            if data and 'message' in data:
                print(f"Message: {data['message']}")
            break
            
        items = data.get('items', [])
        
        if not items:
            break
            
        for item in items:
            commit_id = item.get('sha')
            commit_date = item.get('commit', {}).get('committer', {}).get('date')
            repo_name = item.get('repository', {}).get('full_name')
            commit_url = item.get('html_url')
            
            commits_data.append({
                'username': username,
                'commit_id': commit_id,
                'date': commit_date,
                'repo_name': repo_name,
                'commit_url': commit_url
            })
            
        if len(items) < 100:
            break
            
        page += 1
        # To avoid secondary rate limits on the Search API (30 requests per minute)
        time.sleep(2)
        
    return commits_data

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_user_commits.py <username>")
        sys.exit(1)
        
    username = sys.argv[1]
    
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN or GH_TOKEN environment variable not set.")
        print("Please run: export GITHUB_TOKEN=your_token_here")
        sys.exit(1)
        
    # We use cloak-preview for the commit search API
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.cloak-preview+json'
    }
    
    # Calculate date 1 year ago
    one_year_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    print(f"Fetching activity for user '{username}' since: {one_year_ago}")
    
    filename = f"{username}_commits.csv"
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['username', 'commit_id', 'date', 'repo_name', 'commit_url']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        commits = get_user_commits(username, headers, one_year_ago)
        print(f"  -> Found {len(commits)} commits.")
        
        for commit in commits:
            writer.writerow(commit)
            
    print(f"\nDone! Results saved to {filename}")

if __name__ == "__main__":
    main()
