import os
import subprocess

class XMLEngine:
    def process_document(self, file_path: str) -> list[str]:
        """
        Runs the Word2XML Perl script on the given document's directory.
        Returns the generated XML file path.
        """
        folder = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        legacy_dir = os.path.join(os.path.dirname(__file__), 'legacy')
        wordtoxml_dir = os.path.join(legacy_dir, 'wordtoxml')
        perl_script = os.path.join(wordtoxml_dir, 'Word2XML_Books.pl')
        
        if not os.path.exists(perl_script):
            raise FileNotFoundError(f"Perl script not found at {perl_script}")
            
        try:
            # Run the Perl script; it expects a directory containing the DOCX
            result = subprocess.run(
                ["perl", perl_script, folder],
                cwd=wordtoxml_dir,  # Run from within wordtoxml so it finds dependencies
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Word2XML Error Output: {e.stderr}\nStdout: {e.stdout}")
            raise RuntimeError(f"XML conversion failed: {e.stderr}")
            
        expected_xml_path = os.path.join(folder, "html", f"{base_name}.xml")
        if os.path.exists(expected_xml_path):
            # We can also return the ZIP and other HTMLs if needed, but XML is primary
            return [expected_xml_path]
        else:
            raise FileNotFoundError(f"Expected XML output not found: {expected_xml_path}\nStdout: {result.stdout}")
