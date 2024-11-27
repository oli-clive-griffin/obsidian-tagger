#! /Users/oliclive-griffin/code/tagger/.venv/bin/python

import os
import json
import sys
import yaml
import anthropic
from pathlib import Path

class ObsidianTagger:
    def __init__(self, vault_path: Path, api_key: str):
        self.vault_path = vault_path
        self.client = anthropic.Anthropic(api_key=api_key)

    def parse_frontmatter(self, content: str) -> dict:
        """Parse YAML frontmatter from markdown content."""
        if not content.startswith('---'):
            return {}
        
        try:
            # Find the second '---' that closes the frontmatter
            end_idx = content[3:].index('---') + 3
            frontmatter = yaml.safe_load(content[3:end_idx])
            return frontmatter if frontmatter else {}
        except Exception:
            return {}

    def get_all_vault_tags(self) -> set[str]:
        """Collect all unique tags from all markdown files in the vault."""
        all_tags = set()
        
        for md_file in self.vault_path.rglob("*.md"):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                frontmatter = self.parse_frontmatter(content)
                if frontmatter and 'tags' in frontmatter:
                    # Handle both string and list formats for tags
                    tags = frontmatter['tags']
                    if isinstance(tags, str):
                        all_tags.add(tags)
                    elif isinstance(tags, list):
                        all_tags.update(tags)
            except Exception as e:
                print(f"Error processing {md_file}: {e}")
                
        return all_tags

    def create_tag_generation_prompt(
        self,
        title: str,
        file_contents: str,
        current_tags: list[str],
        vault_tags: set[str]
    ) -> str:
        """Create a prompt for the Claude API to generate relevant tags."""
        return f"""You are a helpful assistant that suggests relevant tags for Obsidian markdown notes.
- Given the following note contents and existing tags, suggest additional relevant tags.
- Only suggest tags that would be genuinely useful for organization and retrieval, and are directly relevant to the note, not just tentatively related.
- Only suggest the "papers" tag if the note is a clipping of the arxiv link itself, not just if it's a note containing the arxiv link. A good heuristic is whether the note's title is the paper title.

Existing tags in vault: {', '.join(sorted(vault_tags))}
Current note tags: {', '.join(current_tags)}

Note contents:

<title>
{title}
</title>

<note>
{file_contents}
</note>

Reply with only a JSON array of suggested new tags. Include both completely new tags and relevant existing vault tags that aren't currently applied to this note.
Example response format: ["tag1", "tag2", "tag3"]"""

    def suggest_tags(
        self,
        title: str,
        file_contents: str,
        current_tags: list[str],
        vault_tags: set[str]
    ) -> list[str]:
        """Get tag suggestions from Claude API."""
        prompt = self.create_tag_generation_prompt(
            title,
            file_contents,
            current_tags,
            vault_tags
        )
        
        response = self.client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        # Parse the JSON array from the response
        if len(response.content) != 1:
            raise ValueError("Expected exactly one response from API")
        
        content = response.content[0]
        if content.type != "text":
            raise ValueError("Expected text response from API")
        
        suggested_tags = json.loads(content.text)
        
        # Ensure we got a list of strings
        if not isinstance(suggested_tags, list) or not all(isinstance(tag, str) for tag in suggested_tags):
            raise ValueError("Invalid response format from API")
            
        return suggested_tags

    def update_frontmatter_tags(
        self,
        content: str,
        new_tags: list[str]
    ) -> str:
        """Update the tags in the frontmatter of the content."""
        if not content.startswith('---'):
            # If no frontmatter exists, create it
            return f"---\ntags: {new_tags}\n---\n\n{content}"
            
        try:
            # Find frontmatter boundaries
            end_idx = content[3:].index('---') + 3
            frontmatter = yaml.safe_load(content[3:end_idx]) or {}
            
            # Update tags
            frontmatter['tags'] = sorted(set(new_tags))
            
            # Reconstruct the document
            new_frontmatter = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True)
            return f"---\n{new_frontmatter}---\n{content[end_idx + 4:]}"
            
        except Exception as e:
            print(f"Error updating frontmatter: {e}")
            return content

    def add_tags(self, filepath: Path) -> None:
        """Main function to add tags to a markdown file."""
        try:
            # Read file contents
            with open(self.vault_path / filepath, 'r', encoding='utf-8') as f:
                contents = f.read()
            
            # Get existing frontmatter
            frontmatter = self.parse_frontmatter(contents)
            current_tags = frontmatter.get('tags', [])
            if isinstance(current_tags, str):
                current_tags = [current_tags]
            
            # Get all vault tags
            vault_tags = self.get_all_vault_tags()
            
            # Get new tag suggestions
            title = Path(filepath).stem
            new_tags = self.suggest_tags(title, contents, current_tags, vault_tags)
            
            # Combine existing and new tags
            all_tags = sorted(set(current_tags + new_tags))
            
            # Update the file
            updated_content = self.update_frontmatter_tags(contents, all_tags)
            
            # Write back to file
            with open(self.vault_path / filepath, 'w', encoding='utf-8') as f:
                f.write(updated_content)
                
            print(f"Successfully updated tags for {filepath}")
            print(f"Added tags: {set(new_tags) - set(current_tags)}")
            
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            raise e

# Example usage
VAULT_PATH = Path("~/main").expanduser()
def main():
    # get from command line args
    if len(sys.argv) < 2:
        print("please provide a filepath")
        return
    
    filepath = ' '.join(sys.argv[1:])
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("please set ANTHROPIC_API_KEY")
        return
    
    tagger = ObsidianTagger(VAULT_PATH, api_key)
    print(f"Adding tags to {filepath}")
    input("Press Enter to continue...")
    tagger.add_tags(Path(filepath))

if __name__ == "__main__":
    main()