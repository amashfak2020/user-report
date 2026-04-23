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

def get_org_members(org_name, headers):
    members = []
    page = 1
    while True:
        url = f"https://api.github.com/orgs/{org_name}/members?page={page}&per_page=100"
        data, status = make_request(url, headers)
        if status != 200:
            print(f"Error fetching members. Status code: {status}")
            if data and 'message' in data:
                print(f"Message: {data['message']}")
            break
        
        if not data:
            break
            
        for user in data:
            members.append(user['login'])
            
        page += 1
    return members

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
        print("Usage: python3 fetch_org_commits.py <org_name>")
        sys.exit(1)
        
    org_name = sys.argv[1]
    
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN or GH_TOKEN environment variable not set.")
        print("Please run: export GITHUB_TOKEN=your_token_here")
        sys.exit(1)
        
    # We use cloak-preview for the commit search API, and standard v3 json for others.
    # The search commit API requires the cloak-preview header.
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.cloak-preview+json'
    }
    
    # Calculate date 1 year ago
    one_year_ago = (datetime.datetime.utcnow() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    print(f"Fetching activity since: {one_year_ago}")
    
    print(f"Fetching members for organization: {org_name}...")
    
    # To fetch members, we shouldn't use cloak-preview, so we temporarily switch
    headers['Accept'] = 'application/vnd.github.v3+json'
    members = get_org_members(org_name, headers)
    
    if not members:
        print("No members found or failed to fetch members. Exiting.")
        sys.exit(1)
        
    print(f"Found {len(members)} members. Fetching commits...")
    
    # Switch back to cloak-preview for commit search
    headers['Accept'] = 'application/vnd.github.cloak-preview+json'
    
    filename = f"{org_name}_commits.csv"
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['username', 'commit_id', 'date', 'repo_name', 'commit_url']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for idx, member in enumerate(members):
            print(f"[{idx+1}/{len(members)}] Fetching commits for {member}...")
            commits = get_user_commits(member, headers, one_year_ago)
            print(f"  -> Found {len(commits)} commits.")
            
            for commit in commits:
                writer.writerow(commit)
            
            # Pause between users to respect the 30 reqs/minute Search API rate limit
            if idx < len(members) - 1:
                time.sleep(2)
            
    print(f"\nDone! Results saved to {filename}")

if __name__ == "__main__":
    main()
