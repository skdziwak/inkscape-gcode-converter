import inkex
from svg.path import Path, Line, Arc, CubicBezier, QuadraticBezier, Close, parse_path, Move
from xml.dom import minidom
import re, sys

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def cubic_bezier(x1, y1, x2, y2, x3, y3, x4, y4, step=0.05):
    t = 0
    while t <= 1:
        x = x1 * (1 - t) ** 3 + 3 * x2 * t * (1 - t) ** 2 + 3 * x3 * t ** 2 * (1 - t) + x4 * t ** 3
        y = y1 * (1 - t) ** 3 + 3 * y2 * t * (1 - t) ** 2 + 3 * y3 * t ** 2 * (1 - t) + y4 * t ** 3
        yield (x, y)
        t += step

def quadratic_bezier(x1, y1, x2, y2, x3, y3, step=0.05):
    t = 0
    while t <= 1:
        x = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * x2 + t ** 2 * x3
        y = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * y2 + t ** 2 * y3
        yield (x, y)
        t += step

class GcodeGenerator(inkex.Effect):
    def __init__(self):
        inkex.Effect.__init__(self)
        self.OptionParser.add_option('--width', action='store', type='int', dest='width', default=220)
        self.OptionParser.add_option('--height', action='store', type='int', dest='height', default=220)
        self.OptionParser.add_option('--max_speed', action='store', type='int', dest='max_speed', default=400)
        self.OptionParser.add_option('--print_speed', action='store', type='int', dest='print_speed', default=40)
        self.OptionParser.add_option('--depth_z', action='store', type='float', dest='depth_z', default=0)
        self.OptionParser.add_option('--print_z', action='store', type='float', dest='print_z', default=0)
        self.OptionParser.add_option('--travel_z', action='store', type='float', dest='travel_z', default=10)
        self.OptionParser.add_option('--invert_y', action='store', type='inkbool', dest='invert_y', default=False)
        self.OptionParser.add_option('--output', action='store', type='string', dest='output', default='output.gcode')

    def transform(self, x, y, matrix):
        x = x * matrix[0] + y * matrix[2] + matrix[4]
        y = x * matrix[1] + y * matrix[3] + matrix[5]
        if self.options.invert_y:
            y = self.options.height - y
        return (x, y)
        
    @staticmethod
    def get_paths(node, matrix=(1,0,0,1,0,0)):
        result = []
        if node.tag.endswith('}svg'):
            for n in node:
                result += GcodeGenerator.get_paths(n, matrix)
        elif node.tag.endswith('}g'):
            if node.get('transform'):
                translate = re.findall(r'translate\s*\(\s*(.*?)\s*,\s*(.*?)\s*\)', node.get('transform'))
                tmatrix = re.findall(r'matrix\s*\(\s*(.*?)\s*,\s*(.*?)\s*,\s*(.*?)\s*,\s*(.*?)\s*,\s*(.*?)\s*,\s*(.*?)\s*\)', node.get('transform'))
                nmatrix = None
                if len(translate) > 0:
                    translate = translate[0]
                    nmatrix = (1, 0, 0, 1, float(translate[0]), float(translate[1]))
                if len(tmatrix) > 0:
                    tmatrix = tmatrix[0]
                    nmatrix = (float(tmatrix[0]), float(tmatrix[1]), float(tmatrix[2]), float(tmatrix[3]), float(tmatrix[4]), float(tmatrix[5]))
                if nmatrix:
                    a = matrix
                    b = nmatrix
                    matrix = (
                        a[0] * b[0] + a[2] * b[1], 
                        a[1] * b[0] + a[3] * b[1],
                        a[0] * b[2] + a[2] * b[3],
                        a[1] * b[2] + a[3] * b[3],
                        a[0] * b[4] + a[2] * b[5] + a[4],
                        a[1] * b[4] + a[3] * b[5] + a[5]
                    )
            for n in node:
                result += GcodeGenerator.get_paths(n, matrix)
        elif node.tag.endswith('}path'):
            result.append((node.get('d'), matrix))
        
        return result

    def effect(self):
        commands = []
        commands.append('G21')
        commands.append('G28')
        commands.append('G90')
        commands.append('M203 X{} Y{}'.format(self.options.max_speed, self.options.max_speed))

        for d, matrix in self.get_paths(self.document.getroot()):
            path = parse_path(d)
            last = None
            for e in path:
                if last == None:
                    commands.append('G0 Z{}'.format(self.options.travel_z))
                    commands.append('M220 S100')
                    p = self.transform(e.start.real, e.start.imag, matrix)
                    commands.append('G1 X{} Y{}'.format(p[0], p[1]))
                last = e
                if isinstance(e, Move):
                    commands.append('G0 Z{}'.format(self.options.travel_z))
                    commands.append('M220 S100')
                    p = self.transform(e.end.real, e.end.imag, matrix)
                    commands.append('G1 X{} Y{}'.format(p[0], p[1]))
                if isinstance(e, Line):
                    commands.append('G0 Z{}'.format(self.options.print_z - self.options.depth_z))
                    commands.append('M220 S{}'.format(self.options.print_speed))
                    p = self.transform(e.end.real, e.end.imag, matrix)
                    commands.append('G1 X{} Y{}'.format(p[0], p[1]))
                if isinstance(e, CubicBezier):
                    commands.append('G0 Z{}'.format(self.options.print_z - self.options.depth_z))
                    commands.append('M220 S{}'.format(self.options.print_speed))
                    for p in cubic_bezier(e.start.real, e.start.imag, e.control1.real, e.control1.imag, 
                                            e.control2.real, e.control2.imag, e.end.real, e.end.imag):
                        p = self.transform(p[0], p[1], matrix)
                        commands.append('G1 X{} Y{}'.format(p[0], p[1]))
                if isinstance(e, QuadraticBezier):
                    commands.append('G0 Z{}'.format(self.options.print_z - self.options.depth_z))
                    commands.append('M220 S{}'.format(self.options.print_speed))
                    for p in quadratic_bezier(e.start.real, e.start.imag, e.control.real, e.control.imag, e.end.real, e.end.imag):
                        p = self.transform(p[0], p[1], matrix)
                        commands.append('G1 X{} Y{}'.format(p[0], p[1]))

        
        commands.append('G0 Z{}'.format(self.options.travel_z))

        s = ''
        for command in commands:
            s += command + '\n'

        with open(self.options.output, 'w') as f:
            f.write(s)

if __name__ == '__main__':
    e = GcodeGenerator()
    e.affect()