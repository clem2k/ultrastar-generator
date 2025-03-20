import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import subprocess
import threading
import queue

# Import configuration variables from your config module (which loads .env)
from config import APP_TITLE, APP_VERSION
from mp3 import fill_artist_title

# Global queue to transfer subprocess output safely to the GUI
output_queue = queue.Queue()

def append_to_console(text):
    """
    Append text to the console widget in a thread-safe way.
    """
    console_text.config(state=tk.NORMAL)
    console_text.insert(tk.END, text)
    console_text.see(tk.END)
    console_text.config(state=tk.DISABLED)

def poll_output_queue():
    """
    Poll the output queue and update the console widget.
    """
    while not output_queue.empty():
        line = output_queue.get()
        append_to_console(line)
    root.after(100, poll_output_queue)

def execute_command(cmd_list, callback=None):
    """
    Execute a command by launching main.py in a subprocess and redirect its output.
    An optional callback is executed on the main thread when the process terminates.
    """
    try:
        process = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    except Exception as e:
        append_to_console(f"Error starting process: {e}\n")
        if callback:
            root.after(0, callback)
        return

    def enqueue_output(pipe):
        for line in iter(pipe.readline, ''):
            output_queue.put(line)
        pipe.close()

    # Start threads to capture stdout and stderr
    threading.Thread(target=enqueue_output, args=(process.stdout,), daemon=True).start()
    threading.Thread(target=enqueue_output, args=(process.stderr,), daemon=True).start()

    # New thread to wait for process termination and notify via the console and callback
    def wait_for_process():
        retcode = process.wait()  # Wait until the process finishes
        output_queue.put(f"\nProcess terminated with return code: {retcode}\n")
        if callback:
            root.after(0, callback)
    threading.Thread(target=wait_for_process, daemon=True).start()

def disable_ui():
    """
    Disable UI elements and display the working message (large and red).
    """
    batch_button.config(state=tk.DISABLED)
    single_mp3_button.config(state=tk.DISABLED)
    # Hide the version label and show the working label in the same cell
    version_label.grid_remove()
    working_label.grid()

def enable_ui():
    """
    Re-enable UI elements and restore the version label.
    """
    batch_button.config(state=tk.NORMAL)
    single_mp3_button.config(state=tk.NORMAL)
    # Hide the working label and show back the version label
    working_label.grid_remove()
    version_label.grid()

def run_batch_mode():
    """
    Launch the application in Batch Mode.
    """
    append_to_console("Launching Batch Mode...\n")
    disable_ui()  # Disable buttons and show working message
    execute_command(["python", "main.py"], callback=enable_ui)

def run_single_mp3_mode():
    """
    Launch the application in Single MP3 Mode by asking the user to select a file.
    If artist or title tags are missing, they are requested via a dialog box.
    """
    from mp3 import read_tags
    
    file_path = filedialog.askopenfilename(
        title="Select MP3 File",
        filetypes=[("MP3 Files", "*.mp3")]
    )
    
    if not file_path:
        messagebox.showwarning("Single MP3 Mode", "No file selected!")
        return

    tags = read_tags(file_path)
    artist = tags.get("artist")
    title = tags.get("title")

    # If tags are missing, ask the user for them
    if not artist or not title:
        import tkinter.simpledialog as simpledialog
        if not artist:
            artist = simpledialog.askstring("Missing Artist", "Please enter the artist:")
        if not title:
            title = simpledialog.askstring("Missing Title", "Please enter the title:")
        # If still missing, notify the user and cancel the process
        if not artist or not title:
            messagebox.showerror("Error", "Artist and Title are required!")
            return

    # Fill the artist and title tags in the MP3 file
    fill_artist_title(file_path, artist, title)
    
    append_to_console(f"Launching Single MP3 Mode with file: {file_path}\n")
    disable_ui()  # Disable UI and show working message
    execute_command(["python", "main.py", file_path], callback=enable_ui)

def main():
    """
    Initialize the main GUI window, configure layout and buttons.
    """
    global root, console_text, batch_button, single_mp3_button, version_label, working_label
    root = tk.Tk()
    root.title(APP_TITLE)
    root.wm_iconname(APP_TITLE)  # Set the window icon name
    root.geometry("800x600")  # Une fenêtre bien spacieuse pour coder en grand !

    # Application title from .env
    title_label = tk.Label(root, text=APP_TITLE, font=("Helvetica", 24))
    title_label.pack(pady=10)
    
    try:
        icon = tk.PhotoImage(file="./assets/logo.png")
        root.iconphoto(True, icon)
    except Exception as e:
        print(f"Erreur lors du chargement de l'icône: {e}")
    
    # Message frame for version and working message (superimposed in the same cell)
    message_frame = tk.Frame(root)
    message_frame.pack(pady=10)
    
    # Version label remains in original style
    version_label = tk.Label(message_frame, text=APP_VERSION)
    version_label.grid(row=0, column=0)
    
    # Working label with larger font and red color, initially hidden
    working_label = tk.Label(message_frame, text="WORKING ... Please wait", font=("Helvetica", 30), fg="red")
    working_label.grid(row=0, column=0)
    working_label.grid_remove()
    
    # Frame for buttons, centered horizontally
    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)
    
    # Uniform buttons with same width
    batch_button = tk.Button(button_frame, text="Batch Mode", width=15, command=run_batch_mode)
    batch_button.grid(row=0, column=0, padx=10)
    
    single_mp3_button = tk.Button(button_frame, text="Single MP3 Mode", width=15, command=run_single_mp3_mode)
    single_mp3_button.grid(row=0, column=1, padx=10)
    
    # Console widget to display subprocess output
    console_text = ScrolledText(root, height=20, state=tk.DISABLED)
    console_text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
    
    # Start polling for output from subprocess
    root.after(100, poll_output_queue)
    
    root.mainloop()

if __name__ == "__main__":
    main()
