import tkinter as tk

'''Some customized tkinter widget subclasses by James Adson. Still very
experimental. Written for Python 3.4'''

class Progressbar(tk.Canvas):
    '''Horizontal progress bar widget that can be configured with different
    colors.

    If a large number of these are used in a single window, it may be helpful to
    manually call the update_idletasks() method on the window to force more
    frequent updates.'''

    BGCOLOR = '#%02x%02x%02x' %(212, 212, 212)
    OUTLINECOLOR = '#%02x%02x%02x' %(122, 122, 122)
    BLUE = '#1E90FF'
    GREEN = '#00E600'
    RED = '#F01E1E'
    GOLD = '#F5DC00'
    GRAY = '#646464'
    PURPLE = '#9932CC'

    def __init__(self, master=None, length=100, color='blue', *args, **kwargs):
        self.barlength = length - 5 #length of inner bar adjusted for padding
        self.height=17
        tk.Canvas.__init__(
            self, master=master, height=20, width=length, 
            highlightthickness=0, *args, **kwargs
            )
        base = self._base_rect(
            length=length, height=self.height, 
            outline=Progressbar.OUTLINECOLOR, fill=Progressbar.BGCOLOR
            )
        #draw prog bar
        self.pbar = self._innerbar(0)

    def _base_rect(self, length, height, outline, fill):
        '''Basic rectangle shape.'''
        pad = 5 #prevents edges of canvas from clipping bar
        top = 5 #top offset
        rnd = 1 #pixels of corner rounding
        l = length - pad #width
        #prevent inner bar from entering into left pad space
        if l < pad:
            return 
        h = height 
        return (
            self.create_polygon(
                pad, top + rnd, #top-left
                pad + rnd, top,

                l - rnd, top, #top-right
                l, top + rnd,

                l, h - rnd, #bottom-right
                l - rnd, h,

                pad + rnd, h, #bottom-left
                pad, h - rnd,
                joinstyle=tk.ROUND, outline=outline, fill=fill)
            )

    def _innerbar(self, length, color=None):
        if not color:
            color = Progressbar.BLUE
        if length < 6:
            length = 6
        #if length < 6:
        #    return (
        #        self.create_rectangle(6,6,6,self.height, fill='', outline='')
        #        )
        return (
            self.create_rectangle(6,6, length,self.height, fill=color, 
                                  outline='')
            )

    def set(self, percent=0, color=None):
        '''Sets progress bar position and bar colorscheme.'''
        if percent < 0 or percent > 100:
            return
        newlength = self.barlength * percent/100
        if newlength < 6:
            newlength = 6
        #self.delete(self.pbar)
        #self.pbar = self._innerbar(newlength, color)
        self.coords(self.pbar, 6,6,newlength,self.height)
        if color:
            self.itemconfig(self.pbar, fill=color)


class RectButton(tk.Frame):
    '''Subclass of tkinter Frame that looks and behaves like a rectangular 
    button.'''
    BGCOLOR = '#%02x%02x%02x' % (235, 235, 235)
    HIGHLIGHT = '#%02x%02x%02x' % (74, 139, 222)

    def __init__(self, master, text='Button', command=None, bg=BGCOLOR):
        self.bgcolor = bg
        self.command = command
        tk.LabelFrame.__init__(self, master, borderwidth=1, relief=tk.GROOVE, 
                               bg=self.bgcolor)
        self.lbl = tk.Label(self, text=text, bg=self.bgcolor)
        self.lbl.pack(expand=True, fill=tk.BOTH, padx=3)
        self.bind('<Button-1>', self._select)
        self.lbl.bind('<Button-1>', self._select)
        self.bind('<ButtonRelease-1>', self._execute)
        self.lbl.bind('<ButtonRelease-1>', self._execute)
        self.bind('<Leave>', self._deselect)
        self.lbl.bind('<Leave>', self._deselect)

    def _select(self, event=None):
        '''Changes the background color to the highlight color'''
        self.selected = True
        self.config(bg=self.HIGHLIGHT)
        self.lbl.config(bg=self.HIGHLIGHT)
        self.update_idletasks()

    def _deselect(self, event=None):
        self.selected = False
        self.config(bg=self.bgcolor)
        self.lbl.config(bg=self.bgcolor)
        return

    def _execute(self, event=None):
        '''Returns the button bgcolor to it's original state.'''
        if self.command and self.selected:
            self.command()
        self._deselect()
            



if __name__ == '__main__':
    '''Show a demo of widgets'''

    root = tk.Tk()
    tk.Label(
        root, text='Progressbar colorscheme defaults to blue. '
        'Can be configured by passing a color argument at construction or '
        'with the set() method.'
        ).pack()
    i = 10
    for color in Progressbar.Colorschemes:
        tk.Label(root, text='color: '+color).pack(padx=100, pady=(1,3))
        pb = Progressbar(root, length=300)
        pb.pack(padx=100, pady=(1, 5))
        pb.set(i, color=color)
        i += 10
    root.mainloop()
